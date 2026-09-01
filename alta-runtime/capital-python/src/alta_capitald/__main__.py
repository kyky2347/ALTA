import argparse
import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .paper_trade import (
    PaperOrderRequest,
    PaperOrderResult,
    PaperTradeConfig,
    TigerPaperSession,
)


def _safe_error_code(error: Exception) -> str | None:
    value = getattr(error, "code", None)
    if value is None:
        return None
    candidate = str(value)
    return candidate if re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", candidate) else None


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="alta_capitald")
    value.add_argument(
        "action",
        choices=("preflight", "snapshot", "open", "close", "flatten", "reconcile"),
    )
    value.add_argument("--config-path", type=Path, required=True)
    value.add_argument("--account-sha256", required=True)
    value.add_argument("--owner-lease-path", type=Path, required=True)
    value.add_argument("--owner-id", required=True)
    value.add_argument("--symbol")
    value.add_argument("--limit-price", type=Decimal)
    value.add_argument("--quantity", type=Decimal)
    value.add_argument("--client-order-id")
    value.add_argument("--order-action", choices=("BUY", "SELL"))
    value.add_argument("--expected-position-before", type=Decimal)
    value.add_argument("--timeout-seconds", type=int, default=20)
    value.add_argument("--max-limit-notional", type=Decimal, default=Decimal("10000"))
    value.add_argument("--quote-known-at", type=datetime.fromisoformat)
    value.add_argument("--max-dispatch-quote-age-seconds", type=int, default=10)
    value.add_argument("--authorization-path", type=Path)
    value.add_argument("--authorization-generation", type=int)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config_path = args.config_path.resolve(strict=True)
        config = PaperTradeConfig(
            config_path=config_path,
            config_root=config_path.parent,
            account_sha256=args.account_sha256,
            owner_id=args.owner_id,
            owner_lease_path=args.owner_lease_path.resolve(),
            timeout_seconds=args.timeout_seconds,
            max_limit_notional=args.max_limit_notional,
            max_dispatch_quote_age_seconds=args.max_dispatch_quote_age_seconds,
            authorization_path=(
                args.authorization_path.resolve(strict=True)
                if args.authorization_path is not None
                else None
            ),
            authorization_generation=args.authorization_generation,
        )
        with TigerPaperSession(config) as session:
            if args.action == "preflight":
                output = session.preflight()
            elif args.action == "snapshot":
                output = session.snapshot()
            else:
                if (
                    args.symbol is None
                    or args.limit_price is None
                    or args.client_order_id is None
                    or args.quantity is None
                ):
                    raise ValueError(
                        "order commands require symbol, limit price, and client identity"
                    )
                if args.action == "open" and args.quote_known_at is None:
                    raise ValueError("open requires a fresh quote timestamp")
                symbol = args.symbol.upper()
                if args.action == "flatten":
                    result = session.flatten_with_identity(
                        symbol, args.limit_price, args.client_order_id
                    )
                else:
                    action = (
                        args.order_action
                        if args.action == "reconcile"
                        else ("BUY" if args.action == "open" else "SELL")
                    )
                    expected_before = (
                        args.expected_position_before
                        if args.action == "reconcile"
                        else (Decimal(0) if args.action == "open" else args.quantity)
                    )
                    if action is None or expected_before is None:
                        raise ValueError(
                            "reconcile requires order action and expected position"
                        )
                    request = PaperOrderRequest(
                        action=action,
                        symbol=symbol,
                        limit_price=args.limit_price,
                        expected_position_before=expected_before,
                        client_order_id=args.client_order_id,
                        quantity=args.quantity,
                        quote_known_at=(
                            args.quote_known_at if args.action == "open" else None
                        ),
                    )
                    result = (
                        session.reconcile(request)
                        if args.action == "reconcile"
                        else session.execute(request)
                    )
                    if result is None:
                        position = session.position(symbol)
                        result = PaperOrderResult(
                            status="unresolved",
                            action=action,
                            symbol=symbol,
                            quantity="0",
                            position_before=str(expected_before),
                            position_after=str(position),
                            average_fill_price=None,
                            broker_order_hash=None,
                        )
                output = result.__dict__
        print(json.dumps({"ok": True, "result": output}, separators=(",", ":")))
        return 0
    except Exception as error:
        fingerprint = hashlib.sha256(
            f"{type(error).__module__}.{type(error).__name__}:{error}".encode()
        ).hexdigest()
        error_code = _safe_error_code(error)
        print(
            json.dumps(
                {
                    "ok": False,
                    "errorType": type(error).__name__,
                    "errorFingerprint": fingerprint,
                    **({"errorCode": error_code} if error_code else {}),
                },
                separators=(",", ":"),
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
