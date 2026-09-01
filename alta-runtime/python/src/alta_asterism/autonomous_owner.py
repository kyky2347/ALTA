import hashlib
import secrets
import threading
from dataclasses import dataclass, field

import psycopg

from .database import AutonomousFenceLost, Database


class AutonomousOwnerBusy(RuntimeError):
    pass


AUTONOMOUS_OWNER_KEY = "alta-autonomous-runner"


@dataclass
class AutonomousOwnerLease:
    """Session ownership paired with a durable, monotonically increasing epoch."""

    database: Database
    connection: psycopg.Connection
    owner_key: str
    epoch: int
    token_digest: str
    backend_pid: int
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _released: bool = field(default=False, repr=False)

    def assert_session(self) -> None:
        """Prove the session that owns the advisory lock is still alive."""

        with self._lock:
            if self._released or self.connection.closed:
                raise AutonomousFenceLost("autonomous owner session is closed")
            try:
                held = self.connection.execute(
                    """WITH owner_lock AS (
                      SELECT hashtextextended(%s, 0) AS lock_key
                    )
                    SELECT EXISTS (
                      SELECT 1 FROM pg_locks, owner_lock
                      WHERE locktype = 'advisory'
                        AND pid = pg_backend_pid()
                        AND granted
                        AND classid::bigint =
                          ((lock_key >> 32) & 4294967295)
                        AND objid::bigint = (lock_key & 4294967295)
                        AND objsubid = 1
                    )""",
                    (self.owner_key,),
                ).fetchone()[0]
            except psycopg.Error as error:
                raise AutonomousFenceLost(
                    "autonomous owner session was disconnected"
                ) from error
            if not held:
                raise AutonomousFenceLost("autonomous advisory ownership was lost")

    def release(self) -> None:
        self.database.drain_autonomous_fence(token_digest=self.token_digest)
        try:
            with self._lock:
                if self._released:
                    return
                self._released = True
                try:
                    self.connection.execute(
                        """UPDATE ops.autonomous_owner
                        SET epoch = epoch + 1,
                            token_digest = %s,
                            backend_pid = NULL,
                            revoked_at = now()
                        WHERE owner_key = %s AND epoch = %s AND token_digest = %s""",
                        (
                            hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
                            self.owner_key,
                            self.epoch,
                            self.token_digest,
                        ),
                    )
                    self.connection.execute(
                        "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                        (self.owner_key,),
                    )
                except psycopg.Error:
                    # A disconnected owner cannot mutate again through this
                    # Database instance. Its successor will advance the epoch.
                    pass
                finally:
                    self.connection.close()
        finally:
            self.database.clear_autonomous_fence(token_digest=self.token_digest)


@dataclass
class MaintenanceOwnerLease:
    """Process-wide writer exclusion used while durable schema may be absent."""

    connection: psycopg.Connection
    owner_key: str
    _released: bool = field(default=False, repr=False)

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            self.connection.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                (self.owner_key,),
            )
        except psycopg.Error:
            pass
        finally:
            self.connection.close()


def acquire_maintenance_owner(database: Database) -> MaintenanceOwnerLease:
    """Exclude every cooperative writer without depending on migrated tables."""

    connection = psycopg.connect(database.dsn, connect_timeout=3, autocommit=True)
    try:
        acquired = connection.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))",
            (AUTONOMOUS_OWNER_KEY,),
        ).fetchone()[0]
    except Exception:
        connection.close()
        raise
    if not acquired:
        connection.close()
        raise AutonomousOwnerBusy("another writer owns the database")
    return MaintenanceOwnerLease(connection, AUTONOMOUS_OWNER_KEY)


def release_maintenance_owner(owner: MaintenanceOwnerLease) -> None:
    owner.release()


def acquire_autonomous_owner(database: Database) -> AutonomousOwnerLease:
    """Acquire and publish the database-wide autonomous writer epoch."""

    owner = psycopg.connect(database.dsn, connect_timeout=3, autocommit=True)
    token_digest = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    try:
        acquired = owner.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))",
            (AUTONOMOUS_OWNER_KEY,),
        ).fetchone()[0]
    except Exception:
        owner.close()
        raise
    if not acquired:
        owner.close()
        raise AutonomousOwnerBusy("another autonomous runner owns the database")
    try:
        backend_pid = owner.execute("SELECT pg_backend_pid()").fetchone()[0]
        epoch = owner.execute(
            """INSERT INTO ops.autonomous_owner
            (owner_key, epoch, token_digest, backend_pid, acquired_at, revoked_at)
            VALUES (%s, 1, %s, %s, now(), NULL)
            ON CONFLICT (owner_key) DO UPDATE SET
              epoch = ops.autonomous_owner.epoch + 1,
              token_digest = EXCLUDED.token_digest,
              backend_pid = EXCLUDED.backend_pid,
              acquired_at = EXCLUDED.acquired_at,
              revoked_at = NULL
            RETURNING epoch""",
            (AUTONOMOUS_OWNER_KEY, token_digest, backend_pid),
        ).fetchone()[0]
        lease = AutonomousOwnerLease(
            database=database,
            connection=owner,
            owner_key=AUTONOMOUS_OWNER_KEY,
            epoch=epoch,
            token_digest=token_digest,
            backend_pid=backend_pid,
        )
        database.activate_autonomous_fence(
            owner_key=AUTONOMOUS_OWNER_KEY,
            epoch=epoch,
            token_digest=token_digest,
            session_validator=lease.assert_session,
        )
    except Exception:
        try:
            owner.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                (AUTONOMOUS_OWNER_KEY,),
            )
        except psycopg.Error:
            pass
        owner.close()
        raise
    return lease


def release_autonomous_owner(owner: AutonomousOwnerLease) -> None:
    owner.release()
