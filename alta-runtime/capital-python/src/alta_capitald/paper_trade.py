import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
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
CLIENT_ORDER_ID_PATTERN = re.compile(r"^alta-[a-f0-9]{32}$")
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


def _order_client_id(order: object) -> str | None:
    value = getattr(order, "user_mark", None)
    return (
        value
        if isinstance(value, str) and CLIENT_ORDER_ID_PATTERN.fullmatch(value)
        else None
    )


def _optional_decimal(value: object) -> str | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return format(result, "f") if result.is_finite() else None


def _known_at(value: object) -> str | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    if timestamp > 10_000_000_000:
        timestamp /= 1000
    try:
        return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def _contract_symbol(value: object) -> str:
    symbol = str(getattr(value, "symbol", "")).upper()
    return symbol if SYMBOL_PATTERN.fullmatch(symbol) else "UNKNOWN"


def _contract_type(value: object) -> str:
    raw = getattr(value, "sec_type", "STK")
    return str(getattr(raw, "value", raw)).rsplit(".", maxsplit=1)[-1].upper()[:16]


def _position_summary(position: object) -> dict[str, object]:
    contract = getattr(position, "contract", None)
    return {
        "symbol": _contract_symbol(contract),
        "securityType": _contract_type(contract),
        "currency": str(getattr(contract, "currency", "USD"))[:8],
        "quantity": _optional_decimal(getattr(position, "quantity", None)),
        "averageCost": _optional_decimal(getattr(position, "average_cost", None)),
        "marketPrice": _optional_decimal(getattr(position, "market_price", None)),
        "marketValue": _optional_decimal(getattr(position, "market_value", None)),
        "unrealizedPnl": _optional_decimal(getattr(position, "unrealized_pnl", None)),
        "unrealizedPnlPercent": _optional_decimal(
            getattr(position, "unrealized_pnl_percent", None)
        ),
        "realizedPnl": _optional_decimal(getattr(position, "realized_pnl", None)),
        "todayPnl": _optional_decimal(getattr(position, "today_pnl", None)),
        "salableQuantity": _optional_decimal(getattr(position, "salable_qty", None)),
    }


def _order_summary(order: object) -> dict[str, object]:
    contract = getattr(order, "contract", None)
    reference = str(getattr(order, "id", "unavailable"))
    return {
        "reference": hashlib.sha256(reference.encode()).hexdigest()[:16],
        "symbol": _contract_symbol(contract),
        "securityType": _contract_type(contract),
        "side": str(getattr(order, "action", "UNKNOWN")).upper()[:8],
        "orderType": str(getattr(order, "order_type", "UNKNOWN")).upper()[:16],
        "status": _order_status(getattr(order, "status", "UNKNOWN")),
        "quantity": _optional_decimal(getattr(order, "quantity", None)),
        "filled": _optional_decimal(getattr(order, "filled", None)),
        "remaining": _optional_decimal(getattr(order, "remaining", None)),
        "limitPrice": _optional_decimal(getattr(order, "limit_price", None)),
        "averageFillPrice": _optional_decimal(getattr(order, "avg_fill_price", None)),
        "commission": _optional_decimal(getattr(order, "commission", None)),
        "realizedPnl": _optional_decimal(getattr(order, "realized_pnl", None)),
        "timeInForce": str(getattr(order, "time_in_force", ""))[:12],
        "outsideRegularHours": getattr(order, "outside_rth", None) is True,
        "createdAt": _known_at(getattr(order, "order_time", None)),
        "updatedAt": _known_at(getattr(order, "update_time", None)),
        "filledAt": _known_at(getattr(order, "trade_time", None)),
    }


@dataclass(frozen=True)
class PaperTradeConfig:
    config_path: Path
    config_root: Path
    account_sha256: str
    owner_id: str
    owner_lease_path: Path
    timeout_seconds: int = 20
    max_limit_notional: Decimal = Decimal("2000")
    authorization_path: Path | None = None
    authorization_generation: int | None = None

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
        if (self.authorization_path is None) != (self.authorization_generation is None):
            raise PaperBoundaryError("Paper authorization binding is incomplete")
        if self.authorization_path is not None:
            if not self.authorization_path.is_absolute():
                raise PaperBoundaryError("Paper authorization path must be absolute")
            if (
                self.authorization_generation is None
                or self.authorization_generation < 1
            ):
                raise PaperBoundaryError("Paper authorization generation is invalid")


@dataclass(frozen=True)
class PaperOrderRequest:
    action: Literal["BUY", "SELL"]
    symbol: str
    limit_price: Decimal
    expected_position_before: Decimal
    client_order_id: str
    quantity: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        if self.action not in ("BUY", "SELL"):
            raise PaperBoundaryError("Paper action is not allowed")
        if CLIENT_ORDER_ID_PATTERN.fullmatch(self.client_order_id) is None:
            raise PaperBoundaryError("Paper client order identity is invalid")
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
    status: Literal["filled", "not_filled", "already_flat", "unresolved"]
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

    def snapshot(self) -> dict[str, object]:
        client, account = self._ready()
        assets = client.get_prime_assets(account=account)
        if assets is None or str(getattr(assets, "account", "")) != account:
            raise PaperBoundaryError("Paper asset response crossed account binding")
        positions = client.get_positions(account=account) or []
        open_orders = client.get_open_orders(account=account) or []
        recent_orders = (
            client.get_orders(
                account=account,
                limit=100,
                is_brief=True,
            )
            or []
        )
        if any(str(getattr(item, "account", "")) != account for item in positions):
            raise PaperBoundaryError("Paper position response crossed account binding")
        if any(str(getattr(item, "account", "")) != account for item in open_orders):
            raise PaperBoundaryError("Paper order response crossed account binding")
        if any(str(getattr(item, "account", "")) != account for item in recent_orders):
            raise PaperBoundaryError("Paper order history crossed account binding")
        segments = getattr(assets, "segments", {}) or {}
        stock = segments.get("S") if isinstance(segments, dict) else None
        asset_summary = {
            "currency": str(getattr(stock, "currency", "USD"))[:8],
            "cashBalance": _optional_decimal(getattr(stock, "cash_balance", None)),
            "cashAvailableForTrade": _optional_decimal(
                getattr(stock, "cash_available_for_trade", None)
            ),
            "netLiquidation": _optional_decimal(
                getattr(stock, "net_liquidation", None)
            ),
            "grossPositionValue": _optional_decimal(
                getattr(stock, "gross_position_value", None)
            ),
            "buyingPower": _optional_decimal(getattr(stock, "buying_power", None)),
            "unrealizedPnl": _optional_decimal(getattr(stock, "unrealized_pl", None)),
            "realizedPnl": _optional_decimal(getattr(stock, "realized_pl", None)),
            "maintenanceMargin": _optional_decimal(
                getattr(stock, "maintain_margin", None)
            ),
        }
        return {
            "paper": True,
            "accountBinding": True,
            "accountFingerprint": hashlib.sha256(account.encode()).hexdigest()[:12],
            "observedAt": datetime.now(tz=UTC).isoformat(),
            "brokerUpdatedAt": _known_at(getattr(assets, "update_timestamp", None)),
            "positionCount": len(positions),
            "openOrderCount": len(open_orders),
            "recentOrderCount": len(recent_orders),
            "mutationPolicy": "one_share_limit_day",
            "assets": asset_summary,
            "positions": [_position_summary(item) for item in positions],
            "orders": [_order_summary(item) for item in recent_orders],
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
        self._assert_mutation_authorized(request.action)
        if request.limit_price * request.quantity > self.config.max_limit_notional:
            raise PaperBoundaryError("Paper order exceeds the notional guard")
        existing = self.reconcile(request)
        if existing is not None:
            if existing.status == "unresolved":
                raise PaperBoundaryError(
                    "Paper client order identity has an unresolved broker history"
                )
            return existing
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
        order.user_mark = request.client_order_id
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
        raise PaperBoundaryError("flatten requires a stable client order identity")

    def flatten_with_identity(
        self, symbol: str, limit_price: Decimal, client_order_id: str
    ) -> PaperOrderResult:
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
                client_order_id=client_order_id,
            )
        )

    def reconcile(self, request: PaperOrderRequest) -> PaperOrderResult | None:
        """Read one stable broker identity without ever placing or cancelling."""

        client, account = self._ready()
        self.lease.assert_owned()
        orders = client.get_orders(account=account, limit=100, is_brief=False) or []
        if any(str(getattr(item, "account", "")) != account for item in orders):
            raise PaperBoundaryError("Paper order history crossed account binding")
        matches = [
            item for item in orders if _order_client_id(item) == request.client_order_id
        ]
        if not matches:
            return None
        if len(matches) != 1:
            raise PaperBoundaryError("Paper client order identity is not unique")
        order = matches[0]
        contract = getattr(order, "contract", None)
        observed = (
            str(getattr(order, "action", "")).rsplit(".", 1)[-1].upper(),
            _contract_symbol(contract),
            _contract_type(contract),
            _decimal(getattr(order, "quantity", 0)),
            _decimal(getattr(order, "limit_price", 0)),
            str(getattr(order, "time_in_force", "")).rsplit(".", 1)[-1].upper(),
            bool(getattr(order, "outside_rth", False)),
        )
        expected = (
            request.action,
            request.symbol,
            "STK",
            request.quantity,
            request.limit_price,
            "DAY",
            False,
        )
        if observed != expected:
            raise PaperBoundaryError(
                "Paper client order identity changed request fields"
            )
        status = _order_status(getattr(order, "status", "UNKNOWN"))
        filled = _decimal(getattr(order, "filled", 0))
        broker_hash = hashlib.sha256(
            str(getattr(order, "id", "unavailable")).encode()
        ).hexdigest()
        position = self.position(request.symbol)
        expected_after = request.expected_position_before + (
            1 if request.action == "BUY" else -1
        )
        if filled == request.quantity and position == expected_after:
            return PaperOrderResult(
                status="filled",
                action=request.action,
                symbol=request.symbol,
                quantity=str(request.quantity),
                position_before=str(request.expected_position_before),
                position_after=str(position),
                average_fill_price=_optional_decimal(
                    getattr(order, "avg_fill_price", request.limit_price)
                ),
                broker_order_hash=broker_hash,
            )
        if (
            status in TERMINAL_ORDER_STATES
            and filled == 0
            and position == request.expected_position_before
        ):
            return PaperOrderResult(
                status="not_filled",
                action=request.action,
                symbol=request.symbol,
                quantity="0",
                position_before=str(request.expected_position_before),
                position_after=str(position),
                average_fill_price=None,
                broker_order_hash=broker_hash,
            )
        return PaperOrderResult(
            status="unresolved",
            action=request.action,
            symbol=request.symbol,
            quantity=str(filled),
            position_before=str(request.expected_position_before),
            position_after=str(position),
            average_fill_price=_optional_decimal(
                getattr(order, "avg_fill_price", None)
            ),
            broker_order_hash=broker_hash,
        )

    def _wait_for_position(self, symbol: str, expected: Decimal) -> Decimal:
        deadline = time.monotonic() + min(self.config.timeout_seconds, 10)
        observed = self.position(symbol)
        while observed != expected and time.monotonic() < deadline:
            time.sleep(0.5)
            observed = self.position(symbol)
        return observed

    def _assert_mutation_authorized(self, action: Literal["BUY", "SELL"]) -> None:
        path = self.config.authorization_path
        generation = self.config.authorization_generation
        if path is None or generation is None:
            raise PaperBoundaryError("Paper mutation authorization is unavailable")
        try:
            metadata = path.lstat()
            if path.is_symlink() or not path.is_file():
                raise PaperBoundaryError(
                    "Paper mutation authorization must be a regular file"
                )
            if metadata.st_mode & 0o077:
                raise PaperBoundaryError(
                    "Paper mutation authorization must be owner-only"
                )
            raw = path.read_text()
            value = json.loads(raw)
        except (OSError, ValueError, TypeError) as error:
            raise PaperBoundaryError(
                "Paper mutation authorization is unreadable"
            ) from error
        configuration_hash = hashlib.sha256(
            self.config.config_path.read_bytes()
        ).hexdigest()
        generation_matches = value.get("generation") == generation or (
            action == "SELL"
            and value.get("closeOnly") is True
            and isinstance(value.get("generation"), int)
            and value["generation"] > generation
        )
        if (
            value.get("version") != 2
            or value.get("enabled") is not True
            or not generation_matches
            or value.get("accountSha256") != self.config.account_sha256
            or value.get("configurationSha256") != configuration_hash
        ):
            raise PaperBoundaryError(
                "Paper mutation authorization was revoked or changed"
            )
        if value.get("closeOnly") is True and action != "SELL":
            raise PaperBoundaryError(
                "Paper authorization is draining and permits close orders only"
            )

    def _ready(self) -> tuple[TradeClient, str]:
        if self.client is None or self.account is None:
            raise PaperBoundaryError("Paper session is not started")
        return self.client, self.account
