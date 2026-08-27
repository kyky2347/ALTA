import hashlib
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from tigeropen.common.util.contract_utils import stock_contract
from tigeropen.common.util.order_utils import limit_order
from tigeropen.tiger_open_config import TigerOpenClientConfig
from tigeropen.trade.trade_client import TradeClient

from .boundary import PaperBoundaryError, SingleOwnerLease

PAPER_ACCOUNT_PATTERN = re.compile(r"^\d{17}$")
SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")
TERMINAL_ORDER_STATES = {"CANCELLED", "EXPIRED", "FILLED", "REJECTED"}


def _decimal(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise PaperBoundaryError("broker returned an invalid number") from error
    if not result.is_finite():
        raise PaperBoundaryError("broker returned a non-finite number")
    return result


def _order_status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw).rsplit(".", maxsplit=1)[-1].upper()


@dataclass(frozen=True)
class PaperTradeConfig:
    config_path: Path
    config_root: Path
    account_sha256: str
    owner_id: str
    owner_lease_path: Path
    timeout_seconds: int = 20
    max_limit_notional: Decimal = Decimal("2000")

    def __post_init__(self) -> None:
        if not self.config_path.is_absolute() or not self.config_root.is_absolute():
            raise PaperBoundaryError("Paper config paths must be absolute")
        root = self.config_root.resolve(strict=True)
        if self.config_path.is_symlink():
            raise PaperBoundaryError("Paper config path cannot be a symlink")
        config = self.config_path.resolve(strict=True)
        if not config.is_file() or not config.is_relative_to(root):
            raise PaperBoundaryError("Paper config path is outside the approved root")
        if config.stat().st_mode & 0o077:
            raise PaperBoundaryError("Paper config permissions must be owner-only")
        if re.fullmatch(r"[a-f0-9]{64}", self.account_sha256) is None:
            raise PaperBoundaryError("Paper account approval hash is invalid")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}", self.owner_id) is None:
            raise PaperBoundaryError("Paper owner ID is invalid")
        if not self.owner_lease_path.is_absolute():
            raise PaperBoundaryError("Paper owner lease path must be absolute")
        if not 5 <= self.timeout_seconds <= 60:
            raise PaperBoundaryError("Paper order timeout must be between 5 and 60")
        if self.max_limit_notional <= 0 or self.max_limit_notional > 10_000:
            raise PaperBoundaryError("Paper order notional guard is invalid")


@dataclass(frozen=True)
class PaperOrderRequest:
    action: Literal["BUY", "SELL"]
    symbol: str
    limit_price: Decimal
    expected_position_before: Decimal
    quantity: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        if self.action not in ("BUY", "SELL"):
            raise PaperBoundaryError("Paper action is not allowed")
        if SYMBOL_PATTERN.fullmatch(self.symbol) is None:
            raise PaperBoundaryError("Paper symbol is invalid")
        if self.quantity != 1:
            raise PaperBoundaryError("Paper acceptance orders are limited to one share")
        if not self.limit_price.is_finite() or self.limit_price <= 0:
            raise PaperBoundaryError("Paper limit price is invalid")
        if (
            self.expected_position_before < 0
            or not self.expected_position_before.is_finite()
        ):
            raise PaperBoundaryError("Paper expected position is invalid")


@dataclass(frozen=True)
class PaperOrderResult:
    status: Literal["filled", "not_filled", "already_flat"]
    action: Literal["BUY", "SELL"]
    symbol: str
    quantity: str
    position_before: str
    position_after: str
    average_fill_price: str | None
    broker_order_hash: str | None


class TigerPaperSession:
    """Executes one-share, limit-only orders against one exact Paper account."""

    def __init__(self, config: PaperTradeConfig) -> None:
        self.config = config
        self.lease = SingleOwnerLease(config.owner_lease_path, config.owner_id)
        self.client_config: TigerOpenClientConfig | None = None
        self.client: TradeClient | None = None
        self.account: str | None = None

    def start(self) -> None:
        self.lease.acquire()
        try:
            client_config = TigerOpenClientConfig(
                enable_dynamic_domain=False,
                props_path=str(self.config.config_path),
            )
            account = str(client_config.account)
            if client_config._sandbox_debug:
                raise PaperBoundaryError("sandbox configuration is not Paper")
            if (
                not client_config.is_paper
                or PAPER_ACCOUNT_PATTERN.fullmatch(account) is None
            ):
                raise PaperBoundaryError(
                    "only a 17-digit Tiger Paper account is allowed"
                )
            if (
                hashlib.sha256(account.encode()).hexdigest()
                != self.config.account_sha256
            ):
                raise PaperBoundaryError(
                    "Paper account does not match explicit approval"
                )
            if not client_config.tiger_id or not client_config.private_key:
                raise PaperBoundaryError("Paper credentials are incomplete")
            client = TradeClient(client_config)
            assets = client.get_prime_assets(account=account)
            if assets is None or str(getattr(assets, "account", "")) != account:
                raise PaperBoundaryError("Paper account preflight binding failed")
            self.client_config = client_config
            self.client = client
            self.account = account
        except Exception:
            self.lease.release()
            raise

    def stop(self) -> None:
        self.client = None
        self.client_config = None
        self.account = None
        self.lease.release()

    def __enter__(self) -> "TigerPaperSession":
        self.start()
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.stop()

    def preflight(self) -> dict[str, object]:
        client, account = self._ready()
        positions = client.get_positions(account=account) or []
        open_orders = client.get_open_orders(account=account) or []
        if any(str(getattr(item, "account", "")) != account for item in positions):
            raise PaperBoundaryError("Paper position response crossed account binding")
        if any(str(getattr(item, "account", "")) != account for item in open_orders):
            raise PaperBoundaryError("Paper order response crossed account binding")
        return {
            "paper": True,
            "accountBinding": True,
            "positionCount": len(positions),
            "openOrderCount": len(open_orders),
            "mutationPolicy": "one_share_limit_day",
        }

    def position(self, symbol: str) -> Decimal:
        if SYMBOL_PATTERN.fullmatch(symbol) is None:
            raise PaperBoundaryError("Paper symbol is invalid")
        client, account = self._ready()
        positions = client.get_positions(account=account, symbol=symbol) or []
        quantity = Decimal(0)
        for position in positions:
            if str(getattr(position, "account", "")) != account:
                raise PaperBoundaryError(
                    "Paper position response crossed account binding"
                )
            contract = getattr(position, "contract", None)
            if str(getattr(contract, "symbol", "")).upper() == symbol:
                quantity += _decimal(getattr(position, "quantity", 0))
        return quantity

    def execute(self, request: PaperOrderRequest) -> PaperOrderResult:
        client, account = self._ready()
        self.lease.assert_owned()
        if request.limit_price * request.quantity > self.config.max_limit_notional:
            raise PaperBoundaryError("Paper order exceeds the notional guard")
        before = self.position(request.symbol)
        if before != request.expected_position_before:
            raise PaperBoundaryError("Paper position changed before order admission")
        expected_after = before + (1 if request.action == "BUY" else -1)
        if expected_after < 0:
            raise PaperBoundaryError("Paper sell would create a short position")
        contract = stock_contract(symbol=request.symbol, currency="USD")
        order = limit_order(
            account,
            contract,
            request.action,
            int(request.quantity),
            float(request.limit_price),
            time_in_force="DAY",
        )
        order.outside_rth = False
        preview = client.preview_order(order)
        warning = (
            preview.get("warning_text")
            if isinstance(preview, dict)
            else getattr(preview, "warning_text", None)
        )
        if warning:
            raise PaperBoundaryError("Paper order preview rejected the request")
        order_id = client.place_order(order)
        if order_id is None:
            raise PaperBoundaryError("Paper broker did not return an order reference")
        broker_hash = hashlib.sha256(str(order_id).encode()).hexdigest()
        deadline = time.monotonic() + self.config.timeout_seconds
        average_fill_price = None
        filled = Decimal(0)
        terminal = False
        while time.monotonic() < deadline:
            observed = client.get_order(account=account, id=int(order_id))
            if observed is None:
                time.sleep(0.5)
                continue
            if str(getattr(observed, "account", "")) != account:
                raise PaperBoundaryError("Paper order response crossed account binding")
            status = _order_status(getattr(observed, "status", ""))
            filled = _decimal(getattr(observed, "filled", 0))
            if filled == request.quantity:
                average_fill_price = str(
                    _decimal(getattr(observed, "avg_fill_price", request.limit_price))
                )
                terminal = True
                break
            if status in TERMINAL_ORDER_STATES:
                terminal = True
                break
            time.sleep(0.5)
        if filled != request.quantity:
            if not terminal:
                client.cancel_order(account=account, id=int(order_id))
                cancellation_deadline = time.monotonic() + min(
                    self.config.timeout_seconds, 10
                )
                while time.monotonic() < cancellation_deadline:
                    observed = client.get_order(account=account, id=int(order_id))
                    if observed is None:
                        time.sleep(0.5)
                        continue
                    if str(getattr(observed, "account", "")) != account:
                        raise PaperBoundaryError(
                            "Paper order response crossed account binding"
                        )
                    status = _order_status(getattr(observed, "status", ""))
                    filled = _decimal(getattr(observed, "filled", 0))
                    if filled == request.quantity or status in TERMINAL_ORDER_STATES:
                        terminal = True
                        if filled == request.quantity:
                            average_fill_price = str(
                                _decimal(
                                    getattr(
                                        observed,
                                        "avg_fill_price",
                                        request.limit_price,
                                    )
                                )
                            )
                        break
                    time.sleep(0.5)
                if not terminal:
                    raise PaperBoundaryError(
                        "Paper order cancellation was not confirmed"
                    )
        if filled != request.quantity:
            after = self._wait_for_position(request.symbol, before)
            if after != before:
                raise PaperBoundaryError("Paper partial fill requires operator review")
            return PaperOrderResult(
                status="not_filled",
                action=request.action,
                symbol=request.symbol,
                quantity="0",
                position_before=str(before),
                position_after=str(after),
                average_fill_price=None,
                broker_order_hash=broker_hash,
            )
        after = self._wait_for_position(request.symbol, expected_after)
        if after != expected_after:
            raise PaperBoundaryError("Paper fill did not reconcile to the position")
        return PaperOrderResult(
            status="filled",
            action=request.action,
            symbol=request.symbol,
            quantity=str(request.quantity),
            position_before=str(before),
            position_after=str(after),
            average_fill_price=average_fill_price,
            broker_order_hash=broker_hash,
        )

    def flatten(self, symbol: str, limit_price: Decimal) -> PaperOrderResult:
        before = self.position(symbol)
        if before == 0:
            return PaperOrderResult(
                status="already_flat",
                action="SELL",
                symbol=symbol,
                quantity="0",
                position_before="0",
                position_after="0",
                average_fill_price=None,
                broker_order_hash=None,
            )
        if before != 1:
            raise PaperBoundaryError(
                "automatic flatten refuses a non-acceptance position"
            )
        return self.execute(
            PaperOrderRequest(
                action="SELL",
                symbol=symbol,
                limit_price=limit_price,
                expected_position_before=before,
            )
        )

    def _wait_for_position(self, symbol: str, expected: Decimal) -> Decimal:
        deadline = time.monotonic() + min(self.config.timeout_seconds, 10)
        observed = self.position(symbol)
        while observed != expected and time.monotonic() < deadline:
            time.sleep(0.5)
            observed = self.position(symbol)
        return observed

    def _ready(self) -> tuple[TradeClient, str]:
        if self.client is None or self.account is None:
            raise PaperBoundaryError("Paper session is not started")
        return self.client, self.account
