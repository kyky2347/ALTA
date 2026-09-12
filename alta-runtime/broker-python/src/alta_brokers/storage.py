"""Private, durable state. Kernel locks survive neither process death nor reboot."""

import hashlib
import json
import os
import sqlite3
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .contracts import BrokerError, Profile, require


def private_directory(path: Path):
    require(path.is_absolute(), "private_path_must_be_absolute")
    # Reject symlink ancestors, including a root that does not yet exist.
    for part in (path, *path.parents):
        require(not part.is_symlink(), "private_path_symlink")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = path.stat()
    require(
        stat.S_ISDIR(metadata.st_mode)
        and metadata.st_uid == os.getuid()
        and not metadata.st_mode & 0o077,
        "private_directory_permissions",
    )
    return path


def read_private(path: Path, *, max_bytes=65536):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        metadata = os.fstat(descriptor)
        require(
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_uid == os.getuid()
            and not metadata.st_mode & 0o077
            and metadata.st_nlink == 1
            and metadata.st_size <= max_bytes,
            "private_file_permissions",
        )
        return json.loads(os.read(descriptor, max_bytes + 1))
    finally:
        os.close(descriptor)


def atomic_private(path: Path, value):
    private_directory(path.parent)
    require(not path.is_symlink(), "private_path_symlink")
    fd, temporary = tempfile.mkstemp(prefix=".broker-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(value, output, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def owner(path: Path):
    import fcntl

    private_directory(path.parent)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        metadata = os.fstat(fd)
        require(
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_uid == os.getuid()
            and not metadata.st_mode & 0o077
            and metadata.st_nlink == 1,
            "owner_lock_permissions",
        )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BrokerError("broker_operation_in_progress") from None
        yield
    finally:
        os.close(fd)


class Ledger:
    def __init__(self, root: Path):
        private_directory(root)
        self.path = root / "ledger.sqlite3"
        for suffix in ("", "-wal", "-shm", "-journal"):
            require(not Path(f"{self.path}{suffix}").is_symlink(), "ledger_symlink")
        fd = os.open(
            self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600
        )
        try:
            metadata = os.fstat(fd)
            require(
                stat.S_ISREG(metadata.st_mode)
                and metadata.st_uid == os.getuid()
                and metadata.st_nlink == 1
                and not metadata.st_mode & 0o077,
                "ledger_permissions",
            )
        finally:
            os.close(fd)
        self.db = sqlite3.connect(self.path, timeout=3)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS intents (
            client_id TEXT PRIMARY KEY, binding TEXT NOT NULL, digest TEXT NOT NULL,
            request TEXT NOT NULL, state TEXT NOT NULL, result TEXT, error TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY, client_id TEXT, event TEXT NOT NULL,
            at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        self.db.commit()

    def get(self, client_id):
        return self.db.execute(
            "SELECT * FROM intents WHERE client_id=?", (client_id,)
        ).fetchone()

    def rows(self):
        return self.db.execute("SELECT * FROM intents ORDER BY rowid").fetchall()

    def flat_and_settled(self):
        """History may remain; unresolved orders or exposure may not."""
        from decimal import Decimal

        from .contracts import Order

        book = {}
        for row in self.rows():
            if row["state"] not in ("filled", "cancelled", "rejected"):
                return False
            if not row["result"]:
                return False
            result = Order.model_validate_json(row["result"])
            book[result.symbol] = book.get(result.symbol, Decimal(0)) + (
                result.filled * (1 if result.side == "BUY" else -1)
            )
        return not any(book.values())

    def prepare(self, profile, intent):
        request = intent.model_dump_json()
        digest = hashlib.sha256(request.encode()).hexdigest()
        current = self.get(intent.client_id)
        if current:
            require(
                current["digest"] == digest and current["binding"] == profile.binding,
                "client_id_conflict",
            )
            return False
        with self.db:
            self.db.execute(
                "INSERT INTO intents(client_id,binding,digest,request,state) VALUES(?,?,?,?,?)",
                (intent.client_id, profile.binding, digest, request, "prepared"),
            )
            self.db.execute(
                "INSERT INTO events(client_id,event) VALUES(?,?)",
                (intent.client_id, "prepared"),
            )
        return True

    def record(self, client_id, state, result=None, error=None):
        with self.db:
            self.db.execute(
                "UPDATE intents SET state=?,result=COALESCE(?,result),error=?,updated_at=CURRENT_TIMESTAMP WHERE client_id=?",
                (state, result.model_dump_json() if result else None, error, client_id),
            )
            self.db.execute(
                "INSERT INTO events(client_id,event) VALUES(?,?)", (client_id, state)
            )

    def close(self):
        self.db.close()


class Profiles:
    def __init__(self, credentials: Path, state: Path, project: Path):
        require(
            not credentials.resolve().is_relative_to(project.resolve()),
            "credentials_inside_project",
        )
        self.credentials = credentials
        self.state = state

    def file(self, provider):
        require(
            provider in ("alpaca", "tiger", "ibkr", "futu", "longport", "schwab"),
            "broker_not_supported",
        )
        return self.credentials / "broker-profiles" / f"{provider}.json"

    def load(self, provider):
        return Profile.model_validate(read_private(self.file(provider)))

    def account_dir(self, profile):
        return self.state / profile.binding

    def save(self, profile, revision):
        with owner(self.state / "profiles.lock"):
            file = self.file(profile.provider)
            previous = self.load(profile.provider) if file.exists() else None
            require(
                revision == (previous.revision if previous else "new"),
                "broker_profile_conflict",
            )
            if previous:
                require(
                    previous.binding == profile.binding,
                    "create_separate_account_profile_required",
                )
                authority = self.account_dir(previous) / "authority.json"
                require(
                    not authority.exists()
                    or read_private(authority).get("mode") == "off",
                    "revoke_before_credential_change",
                )
                ledger = Ledger(self.account_dir(previous))
                try:
                    require(
                        not ledger.rows(),
                        "ledger_migration_required_before_credential_change",
                    )
                finally:
                    ledger.close()
            value = profile.model_dump(mode="json")
            value["account"] = profile.account.get_secret_value()
            value["credentials"] = {
                k: v.get_secret_value() for k, v in profile.credentials.items()
            }
            atomic_private(file, value)
