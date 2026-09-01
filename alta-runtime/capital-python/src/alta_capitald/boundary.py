import json
import os
import re
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from uuid import uuid4

READ_CAPABILITIES = ("snapshot.read",)
ACCOUNT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")


class PaperBoundaryError(RuntimeError):
    pass


class CapitalMode(StrEnum):
    DISABLED = "disabled"
    FAKE = "fake"
    READ_ONLY = "read_only"


@dataclass(frozen=True)
class PaperBoundaryConfig:
    mode: CapitalMode = CapitalMode.DISABLED
    config_path: Path | None = None
    config_root: Path | None = None
    approved_account_id: str | None = None
    approved_account_type: str | None = None
    owner_id: str | None = None
    owner_lease_path: Path | None = None
    paper_mutation_enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.mode, CapitalMode):
            raise PaperBoundaryError("capital mode is not allowed")
        if self.paper_mutation_enabled:
            raise PaperBoundaryError("Paper mutation is unavailable in Bootstrap B5")
        if self.mode == CapitalMode.DISABLED:
            if any(
                value is not None
                for value in (
                    self.config_path,
                    self.config_root,
                    self.approved_account_id,
                    self.approved_account_type,
                    self.owner_id,
                    self.owner_lease_path,
                )
            ):
                raise PaperBoundaryError("disabled mode cannot carry Paper selectors")
            return
        if self.config_path is None or not self.config_path.is_absolute():
            raise PaperBoundaryError(
                "an explicit absolute Paper config path is required"
            )
        if self.config_root is None or not self.config_root.is_absolute():
            raise PaperBoundaryError(
                "an explicit absolute Paper config root is required"
            )
        root = self.config_root.resolve(strict=True)
        if self.config_path.is_symlink():
            raise PaperBoundaryError("Paper config path cannot be a symlink")
        config = self.config_path.resolve(strict=True)
        if not config.is_file() or not config.is_relative_to(root):
            raise PaperBoundaryError("Paper config path is outside the approved root")
        if config.stat().st_mode & 0o077:
            raise PaperBoundaryError("Paper config permissions must be owner-only")
        if (
            self.approved_account_id is None
            or ACCOUNT_PATTERN.fullmatch(self.approved_account_id) is None
            or any(token in self.approved_account_id for token in ("*", "?", "[", "]"))
        ):
            raise PaperBoundaryError("one exact approved Paper account ID is required")
        if self.approved_account_type != "PAPER":
            raise PaperBoundaryError("approved account type must be exactly PAPER")
        if self.owner_id is None or ACCOUNT_PATTERN.fullmatch(self.owner_id) is None:
            raise PaperBoundaryError("an explicit owner ID is required")
        if self.owner_lease_path is None or not self.owner_lease_path.is_absolute():
            raise PaperBoundaryError(
                "an explicit absolute owner lease path is required"
            )


@dataclass(frozen=True)
class PaperSnapshot:
    environment: str
    account_id: str
    account_type: str
    known_at: datetime
    cash: str
    positions: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.known_at.tzinfo is None or self.known_at.utcoffset() is None:
            raise PaperBoundaryError("snapshot known_at must be timezone-aware")
        if len(self.positions) > 500:
            raise PaperBoundaryError("snapshot contains too many positions")
        symbols = [item[0] for item in self.positions]
        if len(symbols) != len(set(symbols)):
            raise PaperBoundaryError("snapshot positions must have unique symbols")
        try:
            cash = Decimal(self.cash)
            quantities = [Decimal(item[1]) for item in self.positions]
        except (InvalidOperation, ValueError) as error:
            raise PaperBoundaryError("snapshot contains an invalid number") from error
        if not cash.is_finite() or cash < 0:
            raise PaperBoundaryError("snapshot cash must be finite and non-negative")
        if any(
            not quantity.is_finite() or abs(quantity) > Decimal("1000000000")
            for quantity in quantities
        ):
            raise PaperBoundaryError("snapshot position quantity is invalid")
        if any(
            ACCOUNT_PATTERN.fullmatch(symbol) is None or len(symbol) > 32
            for symbol in symbols
        ):
            raise PaperBoundaryError("snapshot position symbol is invalid")


class ReadTransport(Protocol):
    def read_snapshot(self, account_id: str, config_path: Path) -> PaperSnapshot: ...


@dataclass
class FakeReadTransport:
    snapshot: PaperSnapshot
    calls: list[tuple[str, str]] = field(default_factory=list)

    def read_snapshot(self, account_id: str, config_path: Path) -> PaperSnapshot:
        self.calls.append((account_id, str(config_path)))
        return self.snapshot


class SingleOwnerLease:
    def __init__(self, path: Path, owner_id: str) -> None:
        if not path.is_absolute():
            raise PaperBoundaryError("owner lease path must be absolute")
        self.path = path
        self.owner_id = owner_id
        self.token: str | None = None
        self.payload: dict[str, object] | None = None

    @property
    def _guard_path(self) -> Path:
        return self.path.with_name(f"{self.path.name}.guard")

    @contextmanager
    def _guard(self):
        """Serialize lease inspection and replacement across local processes."""

        import fcntl

        descriptor = os.open(self._guard_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @staticmethod
    def _process_alive(pid: object) -> bool:
        if not isinstance(pid, int) or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @staticmethod
    def _process_identity(pid: int) -> str | None:
        """Return a stable identity for one process lifetime, not just its PID."""

        proc_stat = Path(f"/proc/{pid}/stat")
        try:
            raw_stat = proc_stat.read_text()
            command_end = raw_stat.rfind(")")
            fields_after_command = raw_stat[command_end + 2 :].split()
            # /proc/<pid>/stat field 22 is the start time in clock ticks. The
            # slice starts at field 3, so field 22 is index 19 here.
            if command_end >= 0 and len(fields_after_command) > 19:
                boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
                start_ticks = fields_after_command[19]
                if boot_id and start_ticks.isdigit():
                    return f"linux:{boot_id}:{start_ticks}"
        except (FileNotFoundError, OSError, UnicodeError):
            pass

        ps_path = "/bin/ps" if Path("/bin/ps").is_file() else "ps"
        try:
            completed = subprocess.run(
                [ps_path, "-p", str(pid), "-o", "lstart="],
                capture_output=True,
                check=False,
                env={"LC_ALL": "C", "PATH": os.environ.get("PATH", "")},
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        started_at = " ".join(completed.stdout.split())
        if completed.returncode != 0 or not started_at:
            return None
        return f"ps:{started_at}"

    def _remove_dead_owner(self) -> None:
        try:
            existing = json.loads(self.path.read_text())
        except FileNotFoundError:
            return
        except (OSError, ValueError, TypeError) as error:
            raise PaperBoundaryError("Paper owner lease is unreadable") from error
        if not isinstance(existing, dict) or "pid" not in existing:
            raise PaperBoundaryError(
                "Paper boundary has a legacy or invalid owner lease"
            )
        existing_pid = existing.get("pid")
        if self._process_alive(existing_pid):
            recorded_identity = existing.get("process_identity")
            if not isinstance(recorded_identity, str) or not recorded_identity:
                # A live legacy lease cannot safely distinguish its owner from
                # a reused PID. Preserve the fail-closed behavior.
                raise PaperBoundaryError("Paper boundary already has an owner")
            current_identity = self._process_identity(existing_pid)
            if current_identity is None:
                raise PaperBoundaryError(
                    "Paper boundary owner identity cannot be verified"
                )
            if current_identity == recorded_identity:
                raise PaperBoundaryError("Paper boundary already has an owner")
        self.path.unlink()

    def _publish(self, payload: bytes, token: str) -> None:
        """Atomically publish a complete lease without a partial-file window."""

        temporary = self.path.with_name(f".{self.path.name}.{token}.tmp")
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor: int | None = None
        try:
            descriptor = os.open(temporary, flags, 0o600)
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("Paper owner lease write made no progress")
                view = view[written:]
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            try:
                os.link(temporary, self.path, follow_symlinks=False)
            except FileExistsError as error:
                raise PaperBoundaryError(
                    "Paper boundary already has an owner"
                ) from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def acquire(self) -> None:
        if self.token is not None:
            return
        token = uuid4().hex
        process_identity = self._process_identity(os.getpid())
        if process_identity is None:
            raise PaperBoundaryError("Paper owner process identity is unavailable")
        lease = {
            "owner_id": self.owner_id,
            "token": token,
            "pid": os.getpid(),
            "process_identity": process_identity,
            "acquired_at": datetime.now(UTC).isoformat(),
        }
        payload = json.dumps(lease, separators=(",", ":")).encode()
        with self._guard():
            if self.path.exists():
                self._remove_dead_owner()
            self._publish(payload, token)
        self.token = token
        self.payload = lease

    def assert_owned(self) -> None:
        if self.token is None:
            raise PaperBoundaryError("Paper boundary owner has not started")
        try:
            payload = json.loads(self.path.read_text())
        except (OSError, ValueError, TypeError) as error:
            raise PaperBoundaryError("Paper owner lease is unavailable") from error
        if payload != self.payload:
            raise PaperBoundaryError("Paper owner lease no longer matches")

    def release(self) -> None:
        if self.token is None:
            return
        self.assert_owned()
        with self._guard():
            self.assert_owned()
            self.path.unlink()
        self.token = None
        self.payload = None


class PaperBoundary:
    def __init__(
        self,
        config: PaperBoundaryConfig,
        transport: ReadTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport
        self.lease = (
            SingleOwnerLease(config.owner_lease_path, config.owner_id)
            if config.mode != CapitalMode.DISABLED
            and config.owner_lease_path is not None
            and config.owner_id is not None
            else None
        )

    def start(self) -> None:
        if self.config.mode == CapitalMode.DISABLED:
            return
        if self.transport is None or self.lease is None:
            raise PaperBoundaryError("read-only boundary is not fully configured")
        self.lease.acquire()

    def stop(self) -> None:
        if self.lease is not None:
            self.lease.release()

    def read_snapshot(self) -> PaperSnapshot:
        if self.config.mode == CapitalMode.DISABLED:
            raise PaperBoundaryError("Paper boundary is disabled")
        if (
            self.transport is None
            or self.lease is None
            or self.config.config_path is None
            or self.config.approved_account_id is None
        ):
            raise PaperBoundaryError("read-only boundary is not fully configured")
        self.lease.assert_owned()
        snapshot = self.transport.read_snapshot(
            self.config.approved_account_id, self.config.config_path
        )
        if snapshot.environment != "PAPER":
            raise PaperBoundaryError("non-Paper response rejected")
        if snapshot.account_type != self.config.approved_account_type:
            raise PaperBoundaryError(
                "broker account type is not the approved Paper type"
            )
        if snapshot.account_id != self.config.approved_account_id:
            raise PaperBoundaryError(
                "response account is not the exact approved account"
            )
        return snapshot
