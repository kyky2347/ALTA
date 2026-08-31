import argparse
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

from .paper_trade import PaperOrderRequest, PaperTradeConfig, TigerPaperSession


def _safe_error_code(error: Exception) -> str | None:
    value = getattr(error, "code", None)
    if value is None:
        return None
    candidate = str(value)
    return candidate if re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", candidate) else None


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="alta_capitald")
    value.add_argument(
        "action", choices=("preflight", "snapshot", "open", "close", "flatten")
    )
    value.add_argument("--config-path", type=Path, required=True)
    value.add_argument("--account-sha256", required=True)
    value.add_argument("--owner-lease-path", type=Path, required=True)
    value.add_argument("--owner-id", required=True)
    value.add_argument("--symbol")
    value.add_argument("--limit-price", type=Decimal)
    value.add_argument("--timeout-seconds", type=int, default=20)
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
        )
        with TigerPaperSession(config) as session:
            if args.action == "preflight":
                output = session.preflight()
            elif args.action == "snapshot":
                output = session.snapshot()
            else:
                if args.symbol is None or args.limit_price is None:
                    raise ValueError("order commands require symbol and limit price")
                symbol = args.symbol.upper()
                if args.action == "flatten":
                    result = session.flatten(symbol, args.limit_price)
                else:
                    result = session.execute(
                        PaperOrderRequest(
                            action="BUY" if args.action == "open" else "SELL",
                            symbol=symbol,
                            limit_price=args.limit_price,
                            expected_position_before=(
                                Decimal(0) if args.action == "open" else Decimal(1)
                            ),
                        )
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
