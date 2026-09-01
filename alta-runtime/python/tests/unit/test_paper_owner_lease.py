import json
import stat
from pathlib import Path

import pytest

from alta_asterism.paper_execution import (
    PAPER_MUTATION_LEASE_PROTOCOL,
    PaperExecutionError,
    TigerPaperExecutor,
    _PaperMutationLease,
)


def test_paper_mutation_lease_fences_pid_reuse_and_token_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = {1: "ps:boot", 42: "ps:process"}
    monkeypatch.setattr("alta_asterism.paper_execution.os.getpid", lambda: 42)
    monkeypatch.setattr(
        "alta_asterism.paper_execution._process_start_identity",
        lambda pid: identity[pid],
    )
    monkeypatch.setattr(
        "alta_asterism.paper_execution.os.kill", lambda _pid, _sig: None
    )
    path = tmp_path / "paper.mutation"
    first = _PaperMutationLease(path, "a" * 64)
    first.acquire()
    stale = json.loads(path.read_text())
    assert stale["protocol"] == PAPER_MUTATION_LEASE_PROTOCOL
    stale["processStartIdentity"] = "ps:reused"
    path.write_text(json.dumps(stale))

    replacement = _PaperMutationLease(path, "a" * 64)
    replacement.acquire()
    with pytest.raises(PaperExecutionError, match="ownership changed"):
        first.release()
    replacement.release()
    assert not path.exists()


def test_paper_mutation_lease_recovers_a_crashed_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("alta_asterism.paper_execution.os.getpid", lambda: 42)
    monkeypatch.setattr(
        "alta_asterism.paper_execution._process_start_identity",
        lambda pid: "ps:boot" if pid == 1 else "ps:process",
    )

    def process_state(pid: int, _signal: int) -> None:
        if pid == 99:
            raise ProcessLookupError

    monkeypatch.setattr("alta_asterism.paper_execution.os.kill", process_state)
    path = tmp_path / "paper.mutation"
    path.write_text(
        json.dumps(
            {
                "protocol": PAPER_MUTATION_LEASE_PROTOCOL,
                "accountSha256": "b" * 64,
                "token": "c" * 64,
                "pid": 99,
                "bootIdentity": "ps:boot",
                "processStartIdentity": "ps:dead",
                "acquiredAt": "2026-08-31T00:00:00+00:00",
            }
        )
    )
    lease = _PaperMutationLease(path, "b" * 64)
    lease.acquire()
    lease.release()


def _executor(repo_root: Path, account_sha256: str) -> TigerPaperExecutor:
    return TigerPaperExecutor(
        repo_root=repo_root,
        config_path=repo_root / "paper.properties",
        account_sha256=account_sha256,
        timeout_seconds=20,
    )


def test_checkouts_share_one_private_lease_for_the_same_paper_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    monkeypatch.setattr("alta_asterism.paper_execution._paper_lease_home", lambda: home)
    monkeypatch.setattr(
        "alta_asterism.paper_execution.shutil.which", lambda _name: "/uv"
    )
    account_hash = "a" * 64

    first = _executor(tmp_path / "checkout-one", account_hash)
    second = _executor(tmp_path / "checkout-two", account_hash)

    assert first.lease_path == second.lease_path
    assert first.lease_path.parent == (home / ".alta" / "capital" / "locks")
    assert stat.S_IMODE(first.lease_path.parent.stat().st_mode) == 0o700


def test_global_paper_lease_is_account_scoped_and_fails_closed_on_bad_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    monkeypatch.setattr("alta_asterism.paper_execution._paper_lease_home", lambda: home)
    monkeypatch.setattr(
        "alta_asterism.paper_execution.shutil.which", lambda _name: "/uv"
    )

    first = _executor(tmp_path / "checkout", "a" * 64)
    second = _executor(tmp_path / "checkout", "b" * 64)
    assert first.lease_path != second.lease_path

    global_root = home / ".alta" / "capital" / "locks"
    global_root.chmod(0o755)
    with pytest.raises(PaperExecutionError, match="owner-only"):
        _executor(tmp_path / "checkout", "c" * 64)


def test_global_paper_lease_rejects_a_symlinked_or_writable_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    (home / ".alta").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr("alta_asterism.paper_execution._paper_lease_home", lambda: home)
    monkeypatch.setattr(
        "alta_asterism.paper_execution.shutil.which", lambda _name: "/uv"
    )

    with pytest.raises(PaperExecutionError, match="symlink"):
        _executor(tmp_path / "checkout", "a" * 64)

    (home / ".alta").unlink()
    (home / ".alta").mkdir(mode=0o700)
    (home / ".alta" / "capital").mkdir(mode=0o700)
    (home / ".alta" / "capital").chmod(0o770)
    with pytest.raises(PaperExecutionError, match="group/other writable"):
        _executor(tmp_path / "checkout", "a" * 64)


def test_global_paper_lease_fails_closed_without_posix_lock_semantics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "alta_asterism.paper_execution._posix_owner_lock_supported", lambda: False
    )
    monkeypatch.setattr(
        "alta_asterism.paper_execution.shutil.which", lambda _name: "/uv"
    )

    with pytest.raises(PaperExecutionError, match="POSIX"):
        _executor(tmp_path / "checkout", "a" * 64)
