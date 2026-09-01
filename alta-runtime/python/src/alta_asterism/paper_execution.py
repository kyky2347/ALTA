import json
import hashlib
import os
import re
import secrets
import shutil
import stat
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

if TYPE_CHECKING:
    from .paper_intent import DurablePaperIntent


class PaperExecutionError(RuntimeError):
    pass


class PaperCapitalCircuitOpen(PaperExecutionError):
    """An uncertain broker mutation that must terminate autonomous execution."""

    pass


ENTRY_LIMIT_OFFSET_BPS = Decimal("25")
EXIT_LIMIT_OFFSET_BPS = Decimal("25")


def _paper_lease_home() -> Path:
    home = Path.home()
    if hasattr(os, "getuid"):
        try:
            import pwd

            home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        except (ImportError, KeyError):
            pass
    return home


def _posix_owner_lock_supported() -> bool:
    return os.name == "posix" and hasattr(os, "getuid")


def _paper_lease_root() -> Path:
    if not _posix_owner_lock_supported():
        raise PaperExecutionError(
            "Tiger Paper execution requires POSIX owner-lock semantics"
        )
    home = _paper_lease_home().resolve(strict=True)
    uid = os.getuid()
    home_metadata = home.stat()
    if not stat.S_ISDIR(home_metadata.st_mode) or home_metadata.st_uid != uid:
        raise PaperExecutionError("Paper owner lease home is not privately owned")
    if home_metadata.st_mode & 0o022:
        raise PaperExecutionError(
            "Paper owner lease home cannot be group/other writable"
        )
    current = home
    for component in (".alta", "capital", "locks"):
        current = current / component
        try:
            current.mkdir(exist_ok=True, mode=0o700)
        except OSError as error:
            raise PaperExecutionError(
                "Paper owner lease directory is unavailable"
            ) from error
        if current.is_symlink():
            raise PaperExecutionError(
                "Paper owner lease directory cannot contain a symlink"
            )
        metadata = current.stat()
        if not stat.S_ISDIR(metadata.st_mode):
            raise PaperExecutionError("Paper owner lease path is not a directory")
        if metadata.st_uid != uid:
            raise PaperExecutionError(
                "Paper owner lease directory has a different owner"
            )
        if metadata.st_mode & 0o022:
            raise PaperExecutionError(
                "Paper owner lease directory cannot be group/other writable"
            )
    return current


def _global_paper_lease_path(account_sha256: str) -> Path:
    """Return one private per-user lease path for an approved Paper account."""

    if re.fullmatch(r"[a-f0-9]{64}", account_sha256) is None:
        raise PaperExecutionError("Paper account approval hash is invalid")
    root = _paper_lease_root()
    metadata = root.stat()
    if metadata.st_mode & 0o077:
        raise PaperExecutionError("Paper owner lease directory must be owner-only")
    resolved = root.resolve(strict=True)
    return resolved / f"tiger-paper-{account_sha256}.owner"


PAPER_MUTATION_LEASE_PROTOCOL = "alta.paper-mutation-lease.v1"


def _process_start_identity(pid: int) -> str:
    try:
        result = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "lstart="],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise PaperExecutionError("Paper process identity is unavailable") from error
    value = " ".join(result.stdout.split())
    if not value:
        raise PaperExecutionError("Paper process identity is unavailable")
    return f"ps:{value}"


class _PaperMutationLease:
    """Process-lifetime lease spanning prepare, broker call, and local commit."""

    def __init__(self, path: Path, account_sha256: str) -> None:
        self.path = path
        self.account_sha256 = account_sha256
        self.acquired = False
        self.token: str | None = None

    def acquire(self) -> None:
        if self.acquired:
            raise PaperExecutionError("Paper mutation lease is already held")
        token = secrets.token_hex(32)
        payload_value = {
            "protocol": PAPER_MUTATION_LEASE_PROTOCOL,
            "accountSha256": self.account_sha256,
            "token": token,
            "pid": os.getpid(),
            "bootIdentity": _process_start_identity(1),
            "processStartIdentity": _process_start_identity(os.getpid()),
            "acquiredAt": datetime.now(UTC).isoformat(),
        }
        payload = (json.dumps(payload_value, separators=(",", ":")) + "\n").encode()
        for attempt in range(2):
            try:
                self._publish(payload, token)
                break
            except FileExistsError as error:
                if attempt:
                    raise PaperExecutionError("Paper mutation lease is busy") from error
                try:
                    raw = self.path.read_bytes()
                    existing = self._validate(json.loads(raw))
                    if self._stale(existing):
                        if self.path.read_bytes() == raw:
                            self.path.unlink()
                            continue
                except (OSError, ValueError, TypeError) as read_error:
                    raise PaperExecutionError(
                        "Paper mutation lease is unreadable"
                    ) from read_error
                raise PaperExecutionError("Paper mutation lease is busy") from error
        else:
            raise PaperExecutionError("Paper mutation lease is unavailable")
        self.token = token
        self.acquired = True

    def _publish(self, payload: bytes, token: str) -> None:
        temporary = self.path.with_name(f".{self.path.name}.{token}.tmp")
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.link(temporary, self.path, follow_symlinks=False)
        finally:
            temporary.unlink(missing_ok=True)

    def _validate(self, value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            raise PaperExecutionError("Paper mutation lease is invalid")
        expected = {
            "protocol",
            "accountSha256",
            "token",
            "pid",
            "bootIdentity",
            "processStartIdentity",
            "acquiredAt",
        }
        if (
            set(value) != expected
            or value.get("protocol") != PAPER_MUTATION_LEASE_PROTOCOL
            or value.get("accountSha256") != self.account_sha256
            or re.fullmatch(r"[a-f0-9]{64}", str(value.get("token"))) is None
            or not isinstance(value.get("pid"), int)
            or value["pid"] <= 0
            or not isinstance(value.get("bootIdentity"), str)
            or not isinstance(value.get("processStartIdentity"), str)
        ):
            raise PaperExecutionError("Paper mutation lease is invalid")
        return value

    @staticmethod
    def _stale(value: dict[str, object]) -> bool:
        if value["bootIdentity"] != _process_start_identity(1):
            return True
        pid = int(value["pid"])
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        try:
            return value["processStartIdentity"] != _process_start_identity(pid)
        except PaperExecutionError:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            except PermissionError:
                return False
            raise

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            payload = self._validate(json.loads(self.path.read_text()))
        except (OSError, ValueError) as error:
            raise PaperExecutionError("Paper mutation lease is unavailable") from error
        if (
            payload.get("pid") != os.getpid()
            or payload.get("token") != self.token
            or payload.get("bootIdentity") != _process_start_identity(1)
            or payload.get("processStartIdentity")
            != _process_start_identity(os.getpid())
        ):
            raise PaperExecutionError("Paper mutation lease ownership changed")
        self.path.unlink()
        self.acquired = False
        self.token = None


class PaperExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["filled", "not_filled", "already_flat", "unresolved"]
    action: Literal["BUY", "SELL"]
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,14}$")
    quantity: str
    position_before: str
    position_after: str
    average_fill_price: str | None
    broker_order_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class DurablePaperPosition(BaseModel):
    """Minimal durable position truth allowed to bind a Paper restart."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    position_id: str = Field(min_length=3, max_length=128)
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,14}$")
    quantity: Decimal
    expression_kind: Literal["stock", "etf"]
    paper_entry_proven: Literal[True]

    @field_validator("quantity")
    @classmethod
    def quantity_is_finite_and_positive(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("durable Paper quantity must be finite and positive")
        return value


class _BrokerPaperPosition(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,14}$")
    security_type: str = Field(alias="securityType")
    quantity: Decimal

    @field_validator("quantity")
    @classmethod
    def quantity_is_finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("broker Paper quantity must be finite")
        return value


class _BrokerPaperSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    paper: Literal[True]
    account_binding: Literal[True] = Field(alias="accountBinding")
    mutation_policy: Literal["one_share_limit_day"] = Field(alias="mutationPolicy")
    position_count: int = Field(alias="positionCount", ge=0, le=500)
    open_order_count: int = Field(alias="openOrderCount", ge=0, le=500)
    positions: tuple[_BrokerPaperPosition, ...] = Field(default=(), max_length=500)

    @model_validator(mode="after")
    def position_count_matches_payload(self) -> "_BrokerPaperSnapshot":
        if self.position_count != len(self.positions):
            raise ValueError("Paper snapshot position count does not match payload")
        return self


class PaperStartupReconciliation(BaseModel):
    """A fail-closed startup decision; it grants no trading authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    posture: Literal["empty", "bound_position"]
    position_id: str | None = None
    symbol: str | None = None

    @model_validator(mode="after")
    def binding_is_complete(self) -> "PaperStartupReconciliation":
        bound = self.posture == "bound_position"
        if bound != (self.position_id is not None and self.symbol is not None):
            raise ValueError("Paper startup binding is incomplete")
        return self


def reconcile_paper_startup(
    snapshot: dict[str, object],
    durable_positions: tuple[DurablePaperPosition, ...],
) -> PaperStartupReconciliation:
    """Allow restart only when broker and durable Paper state agree exactly."""

    try:
        broker = _BrokerPaperSnapshot.model_validate(snapshot)
    except ValidationError as error:
        raise PaperExecutionError("Paper startup snapshot is invalid") from error
    if broker.open_order_count != 0:
        raise PaperExecutionError("Paper startup found an unresolved broker order")
    if len(durable_positions) > 1:
        raise PaperExecutionError("Paper startup found multiple durable positions")
    if not durable_positions and not broker.positions:
        return PaperStartupReconciliation(posture="empty")
    if len(durable_positions) != 1 or len(broker.positions) != 1:
        raise PaperExecutionError("Paper startup found an orphan position")

    durable = durable_positions[0]
    observed = broker.positions[0]
    if durable.quantity != Decimal(1):
        raise PaperExecutionError("Paper durable position is outside one-share policy")
    if observed.security_type.upper() != "STK" or observed.quantity != Decimal(1):
        raise PaperExecutionError("Paper broker position is outside one-share policy")
    if observed.symbol != durable.symbol:
        raise PaperExecutionError("Paper broker position does not match durable state")
    return PaperStartupReconciliation(
        posture="bound_position",
        position_id=durable.position_id,
        symbol=durable.symbol,
    )


class TigerPaperExecutor:
    """Calls the isolated Paper process; it is never exposed as an Agent tool."""

    def __init__(
        self,
        *,
        repo_root: Path,
        config_path: Path,
        account_sha256: str,
        timeout_seconds: int,
        authorization_path: Path | None = None,
        authorization_generation: int | None = None,
        owner_lease_path: Path | None = None,
        mutation_lease_path: Path | None = None,
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
        expected_owner = _global_paper_lease_path(account_sha256)
        self.lease_path = owner_lease_path or expected_owner
        if self.lease_path != expected_owner:
            raise PaperExecutionError("Paper owner lease path is not account-global")
        self.authorization_path = authorization_path
        self.authorization_generation = authorization_generation
        self.mutation_lease_path = mutation_lease_path or Path(
            f"{self.lease_path}.mutation"
        )
        if self.mutation_lease_path != Path(f"{self.lease_path}.mutation"):
            raise PaperExecutionError("Paper mutation lease path is not account-global")

    @contextmanager
    def mutation(self):
        lease = _PaperMutationLease(self.mutation_lease_path, self.account_sha256)
        lease.acquire()
        try:
            yield
        finally:
            lease.release()

    def assert_authorized(self, action: Literal["BUY", "SELL"]) -> None:
        value = self._authorization()
        generation = self.authorization_generation
        assert generation is not None
        generation_matches = value.get("generation") == generation or (
            action == "SELL"
            and value.get("closeOnly") is True
            and value["generation"] > generation
        )
        if not generation_matches:
            raise PaperExecutionError("Paper authorization was revoked or changed")
        if value.get("closeOnly") is True and action != "SELL":
            raise PaperExecutionError(
                "Paper authorization is draining and permits closes only"
            )

    def drain_generation(self) -> int | None:
        value = self._authorization()
        generation = self.authorization_generation
        assert generation is not None
        observed = value["generation"]
        if value.get("closeOnly") is True and observed >= generation:
            return observed
        return None

    def _authorization(self) -> dict[str, object]:
        path = self.authorization_path
        generation = self.authorization_generation
        if path is None or generation is None:
            raise PaperExecutionError("Paper mutation authorization is unavailable")
        try:
            metadata = path.lstat()
            if path.is_symlink() or not path.is_file() or metadata.st_mode & 0o077:
                raise PaperExecutionError("Paper authorization file is not private")
            value = json.loads(path.read_text())
        except (OSError, ValueError, TypeError) as error:
            raise PaperExecutionError(
                "Paper authorization file is unreadable"
            ) from error
        configuration_hash = hashlib.sha256(self.config_path.read_bytes()).hexdigest()
        if (
            value.get("version") != 2
            or value.get("enabled") is not True
            or not isinstance(value.get("generation"), int)
            or value["generation"] < 1
            or value.get("accountSha256") != self.account_sha256
            or value.get("configurationSha256") != configuration_hash
        ):
            raise PaperExecutionError("Paper authorization was revoked or changed")
        return value

    @property
    def enabled(self) -> bool:
        return True

    def preflight(self) -> dict[str, object]:
        return self._invoke("preflight", owner_id="paper-preflight")

    def snapshot(self) -> dict[str, object]:
        return self._invoke("snapshot", owner_id="paper-snapshot")

    def open(
        self,
        symbol: str,
        ask: Decimal,
        cycle_id: str,
        *,
        client_order_id: str,
        limit_offset_bps: Decimal = ENTRY_LIMIT_OFFSET_BPS,
        absolute_limit_price: Decimal | None = None,
    ) -> PaperExecutionResult:
        limit_price = self.open_limit_price(
            ask,
            limit_offset_bps=limit_offset_bps,
            absolute_limit_price=absolute_limit_price,
        )
        return PaperExecutionResult.model_validate(
            self._invoke(
                "open",
                owner_id=self._owner(cycle_id, "open"),
                symbol=symbol,
                limit_price=limit_price,
                client_order_id=client_order_id,
            )
        )

    def close(
        self,
        symbol: str,
        bid: Decimal,
        cycle_id: str,
        *,
        client_order_id: str,
        limit_offset_bps: Decimal = EXIT_LIMIT_OFFSET_BPS,
    ) -> PaperExecutionResult:
        limit_price = self.close_limit_price(bid, limit_offset_bps=limit_offset_bps)
        return PaperExecutionResult.model_validate(
            self._invoke(
                "close",
                owner_id=self._owner(cycle_id, "close"),
                symbol=symbol,
                limit_price=limit_price,
                client_order_id=client_order_id,
            )
        )

    def flatten(
        self,
        symbol: str,
        bid: Decimal,
        cycle_id: str,
        *,
        client_order_id: str,
    ) -> PaperExecutionResult:
        limit_price = (bid * Decimal("0.97")).quantize(
            Decimal("0.01"), rounding=ROUND_DOWN
        )
        return PaperExecutionResult.model_validate(
            self._invoke(
                "flatten",
                owner_id=self._owner(cycle_id, "flatten"),
                symbol=symbol,
                limit_price=limit_price,
                client_order_id=client_order_id,
            )
        )

    def reconcile(self, intent: "DurablePaperIntent") -> PaperExecutionResult:
        return PaperExecutionResult.model_validate(
            self._invoke(
                "reconcile",
                owner_id=self._owner(intent.cycle_id, "reconcile"),
                symbol=intent.symbol,
                limit_price=intent.limit_price,
                client_order_id=intent.client_order_id,
                order_action=intent.action,
                expected_position_before=intent.expected_position_before,
            )
        )

    @classmethod
    def open_limit_price(
        cls,
        ask: Decimal,
        *,
        limit_offset_bps: Decimal = ENTRY_LIMIT_OFFSET_BPS,
        absolute_limit_price: Decimal | None = None,
    ) -> Decimal:
        offset = cls._limit_offset(limit_offset_bps)
        if absolute_limit_price is not None and (
            not absolute_limit_price.is_finite() or absolute_limit_price <= 0
        ):
            raise PaperExecutionError("Paper absolute limit price must be positive")
        return (
            absolute_limit_price
            if absolute_limit_price is not None
            else ask * (Decimal(1) + offset / Decimal(10_000))
        ).quantize(Decimal("0.01"), rounding=ROUND_UP)

    @classmethod
    def close_limit_price(
        cls,
        bid: Decimal,
        *,
        limit_offset_bps: Decimal = EXIT_LIMIT_OFFSET_BPS,
    ) -> Decimal:
        offset = cls._limit_offset(limit_offset_bps)
        return (bid * (Decimal(1) - offset / Decimal(10_000))).quantize(
            Decimal("0.01"), rounding=ROUND_DOWN
        )

    def _invoke(
        self,
        action: str,
        *,
        owner_id: str,
        symbol: str | None = None,
        limit_price: Decimal | None = None,
        client_order_id: str | None = None,
        order_action: str | None = None,
        expected_position_before: Decimal | None = None,
    ) -> dict:
        command = self._command(
            action,
            owner_id=owner_id,
            symbol=symbol,
            limit_price=limit_price,
            client_order_id=client_order_id,
            order_action=order_action,
            expected_position_before=expected_position_before,
        )
        completed = subprocess.run(
            command,
            cwd=self.repo_root,
            env=self._isolated_environment(),
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds + 30,
            check=False,
        )
        return self._decode(completed)

    def _command(
        self,
        action: str,
        *,
        owner_id: str,
        symbol: str | None,
        limit_price: Decimal | None,
        client_order_id: str | None,
        order_action: str | None,
        expected_position_before: Decimal | None,
    ) -> list[str]:
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
        if client_order_id is not None:
            command.extend(["--client-order-id", client_order_id])
        if order_action is not None:
            command.extend(["--order-action", order_action])
        if expected_position_before is not None:
            command.extend(
                ["--expected-position-before", format(expected_position_before, "f")]
            )
        if action in {"open", "close", "flatten"}:
            if self.authorization_path is None or self.authorization_generation is None:
                raise PaperExecutionError(
                    "Paper mutation has no durable authorization generation"
                )
            command.extend(
                [
                    "--authorization-path",
                    str(self.authorization_path),
                    "--authorization-generation",
                    str(self.authorization_generation),
                ]
            )
        return command

    def _isolated_environment(self) -> dict[str, str]:
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
        return environment

    @staticmethod
    def _decode(completed) -> dict:
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
