import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4


class HostLeaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class HostLease:
    credential_slot_id: str
    lease_id: str
    owner_pid: int
    owner_started_at_ms: int


class HostLeaseStore:
    def __init__(
        self,
        root: Path,
        *,
        now_ms: Callable[[], int] = lambda: int(time.time() * 1_000),
        random_id: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        if not root.is_absolute():
            raise HostLeaseError("Massive host lease root must be absolute")
        self.root = root.resolve()
        self.now_ms = now_ms
        self.random_id = random_id
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)

    def acquire(
        self,
        credential_slot_id: str,
        owner_label: str,
        owner_pid: int,
        owner_started_at_ms: int,
        ttl_ms: int,
    ) -> HostLease:
        self._bounded(credential_slot_id, "credential slot ID")
        self._bounded(owner_label, "owner label")
        if min(owner_pid, owner_started_at_ms, ttl_ms) <= 0:
            raise HostLeaseError("Massive host lease owner and TTL must be positive")
        directory = self._directory(credential_slot_id)
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError as error:
            raise HostLeaseError(
                "Massive credential slot already has an owner"
            ) from error
        lease = HostLease(
            credential_slot_id=credential_slot_id,
            lease_id=self.random_id(),
            owner_pid=owner_pid,
            owner_started_at_ms=owner_started_at_ms,
        )
        payload = {
            "schemaVersion": 1,
            "credentialSlotId": credential_slot_id,
            "ownerLabel": owner_label,
            "ownerPid": owner_pid,
            "ownerStartedAtMs": owner_started_at_ms,
            "leaseId": lease.lease_id,
            "heartbeatAtMs": self.now_ms(),
            "ttlMs": ttl_ms,
        }
        try:
            self._write(directory / "lease.json", payload)
        except Exception:
            directory.rmdir()
            raise
        return lease

    def assert_owned(self, lease: HostLease) -> None:
        payload = self._read(self._directory(lease.credential_slot_id) / "lease.json")
        if (
            payload["credentialSlotId"] != lease.credential_slot_id
            or payload["leaseId"] != lease.lease_id
            or payload["ownerPid"] != lease.owner_pid
            or payload["ownerStartedAtMs"] != lease.owner_started_at_ms
        ):
            raise HostLeaseError("Massive host lease owner does not match")
        if self.now_ms() - payload["heartbeatAtMs"] >= payload["ttlMs"]:
            raise HostLeaseError("Massive host lease expired")

    def heartbeat(self, lease: HostLease) -> None:
        self.assert_owned(lease)
        path = self._directory(lease.credential_slot_id) / "lease.json"
        payload = self._read(path)
        payload["heartbeatAtMs"] = self.now_ms()
        self._write(path, payload)

    def release(self, lease: HostLease) -> None:
        self.assert_owned(lease)
        directory = self._directory(lease.credential_slot_id)
        entries = list(directory.iterdir())
        if entries != [directory / "lease.json"]:
            raise HostLeaseError("Massive host lease state is uncertain")
        entries[0].unlink()
        directory.rmdir()

    def record_cooldown(self, lease: HostLease, retry_after: float) -> None:
        if retry_after <= 0:
            raise HostLeaseError("Massive cooldown must be positive")
        self.assert_owned(lease)
        self._write(
            self._cooldown_path(lease.credential_slot_id),
            {
                "schemaVersion": 1,
                "credentialSlotId": lease.credential_slot_id,
                "untilMs": self.now_ms() + int(retry_after * 1_000),
            },
        )

    def cooldown_remaining(self, lease: HostLease) -> float:
        self.assert_owned(lease)
        path = self._cooldown_path(lease.credential_slot_id)
        if not path.exists():
            return 0
        payload = self._read_cooldown(path, lease.credential_slot_id)
        return max(0, (payload["untilMs"] - self.now_ms()) / 1_000)

    def _directory(self, credential_slot_id: str) -> Path:
        digest = hashlib.sha256(credential_slot_id.encode()).hexdigest()
        return self.root / digest

    def _cooldown_path(self, credential_slot_id: str) -> Path:
        digest = hashlib.sha256(credential_slot_id.encode()).hexdigest()
        return self.root / f"{digest}.cooldown.json"

    @staticmethod
    def _bounded(value: str, name: str) -> None:
        if not value or len(value) > 128:
            raise HostLeaseError(f"Massive {name} is invalid")

    def _read(self, path: Path) -> dict:
        try:
            value = json.loads(path.read_text())
        except (OSError, ValueError, TypeError) as error:
            raise HostLeaseError("Massive host lease state is unavailable") from error
        expected = {
            "schemaVersion",
            "credentialSlotId",
            "ownerLabel",
            "ownerPid",
            "ownerStartedAtMs",
            "leaseId",
            "heartbeatAtMs",
            "ttlMs",
        }
        if (
            not isinstance(value, dict)
            or set(value) != expected
            or value.get("schemaVersion") != 1
            or any(
                not isinstance(value.get(key), int) or value[key] <= 0
                for key in ("ownerPid", "ownerStartedAtMs", "heartbeatAtMs", "ttlMs")
            )
        ):
            raise HostLeaseError("Massive host lease state is invalid")
        return value

    @staticmethod
    def _read_cooldown(path: Path, credential_slot_id: str) -> dict:
        try:
            value = json.loads(path.read_text())
        except (OSError, ValueError, TypeError) as error:
            raise HostLeaseError("Massive cooldown state is unavailable") from error
        if (
            not isinstance(value, dict)
            or set(value) != {"schemaVersion", "credentialSlotId", "untilMs"}
            or value.get("schemaVersion") != 1
            or value.get("credentialSlotId") != credential_slot_id
            or not isinstance(value.get("untilMs"), int)
        ):
            raise HostLeaseError("Massive cooldown state is invalid")
        return value

    def _write(self, path: Path, value: dict) -> None:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(
                descriptor,
                (
                    json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n"
                ).encode(),
            )
        finally:
            os.close(descriptor)
        temporary.replace(path)
        os.chmod(path, 0o600)
