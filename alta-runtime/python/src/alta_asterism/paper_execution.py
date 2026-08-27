import json
import os
import shutil
import subprocess
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PaperExecutionError(RuntimeError):
    pass


ENTRY_LIMIT_OFFSET_BPS = Decimal("25")
EXIT_LIMIT_OFFSET_BPS = Decimal("25")


class PaperExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["filled", "not_filled", "already_flat"]
    action: Literal["BUY", "SELL"]
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,14}$")
    quantity: str
    position_before: str
    position_after: str
    average_fill_price: str | None
    broker_order_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class TigerPaperExecutor:
    """Calls the isolated Paper process; it is never exposed as an Agent tool."""

    def __init__(
        self,
        *,
        repo_root: Path,
        config_path: Path,
        account_sha256: str,
        timeout_seconds: int,
    ) -> None:
        uv = shutil.which("uv")
        if uv is None:
            raise PaperExecutionError("uv is required for the isolated Paper process")
        self.repo_root = repo_root
        self.project = repo_root / "alta-runtime" / "capital-python"
        self.config_path = config_path
        self.account_sha256 = account_sha256
        self.timeout_seconds = timeout_seconds
        self.uv = uv
        self.lease_path = repo_root / ".alta" / "locks" / "tiger-paper.owner"
        self.lease_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    @property
    def enabled(self) -> bool:
        return True

    def preflight(self) -> dict[str, object]:
        return self._invoke("preflight", owner_id="paper-preflight")

    def open(
        self,
        symbol: str,
        ask: Decimal,
        cycle_id: str,
        *,
        limit_offset_bps: Decimal = ENTRY_LIMIT_OFFSET_BPS,
        absolute_limit_price: Decimal | None = None,
    ) -> PaperExecutionResult:
        offset = self._limit_offset(limit_offset_bps)
        if absolute_limit_price is not None and (
            not absolute_limit_price.is_finite() or absolute_limit_price <= 0
        ):
            raise PaperExecutionError("Paper absolute limit price must be positive")
        limit_price = (
            absolute_limit_price
            if absolute_limit_price is not None
            else ask * (Decimal(1) + offset / Decimal(10_000))
        ).quantize(Decimal("0.01"), rounding=ROUND_UP)
        return PaperExecutionResult.model_validate(
            self._invoke(
                "open",
                owner_id=self._owner(cycle_id, "open"),
                symbol=symbol,
                limit_price=limit_price,
            )
        )

    def close(
        self,
        symbol: str,
        bid: Decimal,
        cycle_id: str,
        *,
        limit_offset_bps: Decimal = EXIT_LIMIT_OFFSET_BPS,
    ) -> PaperExecutionResult:
        offset = self._limit_offset(limit_offset_bps)
        limit_price = (bid * (Decimal(1) - offset / Decimal(10_000))).quantize(
            Decimal("0.01"), rounding=ROUND_DOWN
        )
        return PaperExecutionResult.model_validate(
            self._invoke(
                "close",
                owner_id=self._owner(cycle_id, "close"),
                symbol=symbol,
                limit_price=limit_price,
            )
        )

    def flatten(self, symbol: str, bid: Decimal, cycle_id: str) -> PaperExecutionResult:
        limit_price = (bid * Decimal("0.97")).quantize(
            Decimal("0.01"), rounding=ROUND_DOWN
        )
        return PaperExecutionResult.model_validate(
            self._invoke(
                "flatten",
                owner_id=self._owner(cycle_id, "flatten"),
                symbol=symbol,
                limit_price=limit_price,
            )
        )

    def _invoke(
        self,
        action: str,
        *,
        owner_id: str,
        symbol: str | None = None,
        limit_price: Decimal | None = None,
    ) -> dict:
        command = [
            self.uv,
            "run",
            "--frozen",
            "--project",
            str(self.project),
            "python",
            "-m",
            "alta_capitald",
            action,
            "--config-path",
            str(self.config_path),
            "--account-sha256",
            self.account_sha256,
            "--owner-lease-path",
            str(self.lease_path),
            "--owner-id",
            owner_id,
            "--timeout-seconds",
            str(self.timeout_seconds),
        ]
        if symbol is not None and limit_price is not None:
            command.extend(
                ["--symbol", symbol, "--limit-price", format(limit_price, "f")]
            )
        environment = {
            key: value
            for key, value in os.environ.items()
            if key
            in {
                "HOME",
                "LANG",
                "PATH",
                "SSL_CERT_FILE",
                "SYSTEMROOT",
                "TEMP",
                "TMP",
                "TMPDIR",
                "USERPROFILE",
            }
            or key.startswith("LC_")
        }
        environment["UV_PROJECT_ENVIRONMENT"] = str(
            self.repo_root / ".alta" / "capital" / "venv"
        )
        completed = subprocess.run(
            command,
            cwd=self.repo_root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds + 30,
            check=False,
        )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if not lines:
            raise PaperExecutionError("isolated Paper process returned no result")
        try:
            payload = json.loads(lines[-1])
        except ValueError as error:
            raise PaperExecutionError("isolated Paper result is invalid") from error
        if completed.returncode != 0 or payload.get("ok") is not True:
            error_type = str(payload.get("errorType", "PaperExecutionFailure"))[:64]
            fingerprint = str(payload.get("errorFingerprint", "unknown"))[:64]
            raise PaperExecutionError(
                f"isolated Paper request failed: {error_type}:{fingerprint}"
            )
        result = payload.get("result")
        if not isinstance(result, dict):
            raise PaperExecutionError("isolated Paper result is missing")
        return result

    @staticmethod
    def _owner(cycle_id: str, action: str) -> str:
        safe_cycle = "".join(
            character if character.isalnum() or character in "._-" else "-"
            for character in cycle_id
        )[:80]
        return f"alta-{safe_cycle}-{action}"

    @staticmethod
    def _limit_offset(value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0 or value > Decimal(25):
            raise PaperExecutionError("Paper limit offset must be between 0 and 25 bps")
        return value
