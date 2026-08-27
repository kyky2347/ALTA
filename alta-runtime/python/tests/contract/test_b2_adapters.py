import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from alta_asterism.ingest import REDACTED, RateLimited, RawReceipt, SourceEnvelope
from alta_asterism.finlight import FinlightAdapter
from alta_asterism.massive import (
    MassiveAccessCoordinator,
    MassiveAccessDecision,
    MassiveAccessEvidence,
    MassiveAccessMode,
    MassiveDataset,
    MassiveRequestBudget,
    MassiveRestAdapter,
    decide_access,
)
from alta_asterism.massive_lease import HostLeaseError, HostLeaseStore

FIXTURES = Path(__file__).parents[1] / "fixtures"


def load_envelope(source: str, name: str) -> SourceEnvelope:
    return SourceEnvelope.model_validate_json((FIXTURES / source / name).read_text())


class MemoryRawSink:
    def __init__(self) -> None:
        self.hashes: set[str] = set()
        self.lock = threading.Lock()

    def save(self, envelope: SourceEnvelope) -> RawReceipt:
        content_hash = envelope.content_hash()
        with self.lock:
            inserted = content_hash not in self.hashes
            self.hashes.add(content_hash)
        return RawReceipt(
            id=f"raw_{content_hash}",
            content_hash=content_hash,
            known_at=datetime(2026, 8, 23, 13, tzinfo=UTC),
            inserted=inserted,
        )


class FakeMonotonic:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


def enabled_shared() -> MassiveAccessEvidence:
    return MassiveAccessEvidence(
        requested_mode=MassiveAccessMode.HOST_COORDINATED,
        credential_slot_id="fixture-slot-reference",
        all_same_key_consumers_coordinated=True,
    )


def shared_coordinator(
    tmp_path: Path,
    cooldown=None,
    now_ms=lambda: int(time.time() * 1_000),
) -> tuple[MassiveAccessCoordinator, HostLeaseStore]:
    root = (tmp_path / "massive-host-lease").resolve()
    store = HostLeaseStore(root, now_ms=now_ms)
    lease = store.acquire(
        "fixture-slot-reference",
        "pytest",
        os.getpid(),
        int(time.time() * 1_000),
        60_000,
    )
    return (
        MassiveAccessCoordinator(
            enabled_shared(), cooldown, lease_store=store, lease=lease
        ),
        store,
    )


def test_content_hash_is_delivery_independent_and_secrets_are_redacted() -> None:
    envelope = load_envelope("finlight", "article_ws.json")
    replayed = envelope.model_copy(
        update={
            "channel": "rest",
            "received_at": envelope.received_at + timedelta(minutes=1),
            "source_url": "https://fixture.invalid/item?api_key=REDACTION_CANARY",
            "payload": {
                **envelope.payload,
                "authorization": "Bearer REDACTION_CANARY",
                "nested": {"client_secret": "REDACTION_CANARY"},
            },
        }
    )
    clean_replayed = replayed.model_copy(
        update={"source_url": envelope.source_url, "payload": envelope.payload}
    )

    assert envelope.content_hash() == clean_replayed.content_hash()
    serialized = json.dumps(replayed.raw_body())
    assert "REDACTION_CANARY" not in serialized
    assert serialized.count(REDACTED) == 3


@pytest.mark.parametrize(
    ("evidence", "verified", "mode", "reason"),
    [
        (
            MassiveAccessEvidence(),
            False,
            MassiveAccessMode.DISABLED,
            "configured_disabled",
        ),
        (
            MassiveAccessEvidence(requested_mode=MassiveAccessMode.DEDICATED),
            False,
            MassiveAccessMode.DISABLED,
            "missing_credential_slot_evidence",
        ),
        (
            MassiveAccessEvidence(
                requested_mode=MassiveAccessMode.DEDICATED,
                credential_slot_id="fixture-slot-reference",
            ),
            False,
            MassiveAccessMode.DISABLED,
            "dedicated_key_not_confirmed",
        ),
        (
            MassiveAccessEvidence(
                requested_mode=MassiveAccessMode.HOST_COORDINATED,
                credential_slot_id="fixture-slot-reference",
            ),
            False,
            MassiveAccessMode.DISABLED,
            "all_same_key_consumers_not_coordinated",
        ),
        (
            MassiveAccessEvidence(
                requested_mode=MassiveAccessMode.DEDICATED,
                credential_slot_id="fixture-slot-reference",
                dedicated_key_confirmed=True,
            ),
            False,
            MassiveAccessMode.DEDICATED,
            "dedicated_confirmed",
        ),
        (
            enabled_shared(),
            True,
            MassiveAccessMode.HOST_COORDINATED,
            "shared_coordinator_confirmed",
        ),
    ],
)
def test_massive_access_is_fail_closed(
    evidence: MassiveAccessEvidence,
    verified: bool,
    mode: MassiveAccessMode,
    reason: str,
) -> None:
    assert decide_access(
        evidence, host_lease_verified=verified
    ) == MassiveAccessDecision(mode, reason)


def test_disabled_massive_never_calls_transport() -> None:
    class Transport:
        calls = 0

        def fetch(self, dataset, symbols):
            self.calls += 1
            return []

    transport = Transport()
    adapter = MassiveRestAdapter(transport, MemoryRawSink(), MassiveAccessCoordinator())

    result = adapter.fetch(MassiveDataset.DAILY_BARS, ["DEMO"])

    assert (result.access_mode, result.posture, transport.calls) == (
        MassiveAccessMode.DISABLED,
        "disabled",
        0,
    )


def test_massive_request_budget_is_per_cycle_and_fail_closed() -> None:
    class Transport:
        calls = 0

        def fetch(self, _dataset, _symbols):
            self.calls += 1
            return []

    transport = Transport()
    budget = MassiveRequestBudget(2)
    coordinator = MassiveAccessCoordinator(
        MassiveAccessEvidence(
            requested_mode=MassiveAccessMode.DEDICATED,
            credential_slot_id="dedicated-fixture",
            dedicated_key_confirmed=True,
        )
    )
    adapter = MassiveRestAdapter(
        transport,
        MemoryRawSink(),
        coordinator,
        request_budget=budget,
    )
    adapter.reset_budget("cycle-one")

    first = adapter.fetch(MassiveDataset.STOCK_SNAPSHOTS, ["SPY"])
    second = adapter.fetch(MassiveDataset.STOCK_SNAPSHOTS, ["SPY"])
    blocked = adapter.fetch(MassiveDataset.STOCK_SNAPSHOTS, ["SPY"])
    adapter.reset_budget("cycle-two")
    recovered = adapter.fetch(MassiveDataset.STOCK_SNAPSHOTS, ["SPY"])

    assert (
        first.posture,
        second.posture,
        blocked.reason,
        recovered.posture,
        transport.calls,
        budget.snapshot(),
    ) == (
        "healthy",
        "healthy",
        "cycle_request_budget_exhausted",
        "healthy",
        3,
        ("cycle-two", 1, 2),
    )


def test_massive_429_obeys_retry_after_without_automatic_retry(tmp_path: Path) -> None:
    clock = FakeMonotonic()
    envelope = load_envelope("massive", "daily_bar.json")

    class Transport:
        calls = 0

        def fetch(self, dataset, symbols):
            self.calls += 1
            if self.calls == 1:

                def partial_batch():
                    yield envelope
                    raise RateLimited(30)

                return partial_batch()
            return [envelope]

    transport = Transport()
    from alta_asterism.ingest import Cooldown

    coordinator, _ = shared_coordinator(
        tmp_path, Cooldown(clock), now_ms=lambda: int(clock.value * 1_000)
    )
    adapter = MassiveRestAdapter(transport, MemoryRawSink(), coordinator)

    first = adapter.fetch(MassiveDataset.DAILY_BARS, ["DEMO"])
    blocked = adapter.fetch(MassiveDataset.DAILY_BARS, ["DEMO"])
    clock.value += 30
    recovered = adapter.fetch(MassiveDataset.DAILY_BARS, ["DEMO"])

    assert (
        first.reason,
        first.inserted,
        blocked.reason,
        recovered.posture,
        recovered.duplicates,
        transport.calls,
    ) == (
        "upstream_429",
        1,
        "retry_after_cooldown",
        "healthy",
        1,
        2,
    )


def test_finlight_429_obeys_retry_after_without_automatic_retry() -> None:
    clock = FakeMonotonic()
    envelope = load_envelope("finlight", "article_ws.json").model_copy(
        update={"channel": "rest"}
    )

    class Owner:
        @contextmanager
        def acquire(self):
            yield

    class Transport:
        websocket_available = False
        calls = 0

        def stream(self, cursor):
            raise AssertionError("polling mode cannot open WS")

        def rest_gap(self, cursor):
            raise AssertionError("polling mode cannot request a WS gap")

        def poll_rest(self, cursor):
            self.calls += 1
            if self.calls == 1:

                def partial_batch():
                    yield envelope
                    raise RateLimited(15)

                return partial_batch()
            return [envelope]

    from alta_asterism.ingest import Cooldown

    transport = Transport()
    adapter = FinlightAdapter(transport, MemoryRawSink(), Owner(), Cooldown(clock))

    first = adapter.run_once()
    blocked = adapter.run_once()
    clock.value += 15
    recovered = adapter.run_once()

    assert (
        first.reason,
        first.inserted,
        blocked.reason,
        recovered.posture,
        recovered.duplicates,
        transport.calls,
    ) == (
        "upstream_429",
        1,
        "retry_after_cooldown",
        "degraded",
        1,
        2,
    )


def test_massive_shared_mode_has_one_global_admission(tmp_path: Path) -> None:
    envelope = load_envelope("massive", "daily_bar.json")

    class Transport:
        def __init__(self) -> None:
            self.active = 0
            self.max_active = 0
            self.lock = threading.Lock()

        def fetch(self, dataset, symbols):
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            time.sleep(0.04)
            try:
                yield envelope
            finally:
                with self.lock:
                    self.active -= 1

    transport = Transport()
    coordinator, _ = shared_coordinator(tmp_path)
    adapter = MassiveRestAdapter(transport, MemoryRawSink(), coordinator)
    results = []
    threads = [
        threading.Thread(
            target=lambda: results.append(
                adapter.fetch(MassiveDataset.DAILY_BARS, ["DEMO"])
            )
        )
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert transport.max_active == 1
    assert [result.posture for result in results] == ["healthy", "healthy"]


@pytest.mark.parametrize("symbols", [["*"], [], [f"X{index}" for index in range(51)]])
def test_massive_forbids_full_market_and_non_small_universe(
    symbols, tmp_path: Path
) -> None:
    class Transport:
        def fetch(self, dataset, symbols):
            return []

    coordinator, _ = shared_coordinator(tmp_path)
    adapter = MassiveRestAdapter(Transport(), MemoryRawSink(), coordinator)

    with pytest.raises(ValueError):
        adapter.fetch(MassiveDataset.DAILY_BARS, symbols)


def test_massive_host_coordination_requires_real_single_owner_lease(
    tmp_path: Path,
) -> None:
    root = (tmp_path / "shared-root").resolve()
    first = HostLeaseStore(root)
    lease = first.acquire(
        "fixture-slot-reference",
        "first",
        os.getpid(),
        int(time.time() * 1_000),
        60_000,
    )
    with pytest.raises(HostLeaseError, match="already has an owner"):
        HostLeaseStore(root).acquire(
            "fixture-slot-reference",
            "second",
            os.getpid() + 1,
            int(time.time() * 1_000),
            60_000,
        )
    first.assert_owned(lease)

    unverified = MassiveAccessCoordinator(enabled_shared())
    assert unverified.decision == MassiveAccessDecision(
        MassiveAccessMode.DISABLED, "all_same_key_consumers_not_coordinated"
    )
