import threading
from collections.abc import Callable, Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from .ingest import Cooldown, RateLimited, RawSink, SourceEnvelope
from .massive_lease import HostLease, HostLeaseError, HostLeaseStore

_HOST_ADMISSIONS: dict[str, threading.BoundedSemaphore] = {}
_HOST_ADMISSIONS_LOCK = threading.Lock()


class MassiveAccessMode(StrEnum):
    DISABLED = "disabled"
    DEDICATED = "dedicated"
    HOST_COORDINATED = "host_coordinated"


class MassiveDataset(StrEnum):
    DAILY_BARS = "daily_bars"
    TICKER_REFERENCE = "ticker_reference"
    STOCK_SNAPSHOTS = "stock_snapshots"


@dataclass(frozen=True)
class OptionChainQuery:
    underlying_symbol: str
    contract_type: str
    expiration_from: date
    expiration_to: date
    strike_from: Decimal | None = None
    strike_to: Decimal | None = None


@dataclass(frozen=True)
class CapturedMassiveRecord:
    envelope: SourceEnvelope
    raw_id: str
    raw_version: int
    content_hash: str
    known_at: datetime


@dataclass(frozen=True)
class MassiveAccessEvidence:
    requested_mode: MassiveAccessMode = MassiveAccessMode.DISABLED
    credential_slot_id: str | None = None
    dedicated_key_confirmed: bool = False
    all_same_key_consumers_coordinated: bool = False


@dataclass(frozen=True)
class MassiveAccessDecision:
    mode: MassiveAccessMode
    reason: str


def decide_access(
    evidence: MassiveAccessEvidence, *, host_lease_verified: bool = False
) -> MassiveAccessDecision:
    if evidence.requested_mode is MassiveAccessMode.DISABLED:
        return MassiveAccessDecision(MassiveAccessMode.DISABLED, "configured_disabled")
    if not evidence.credential_slot_id:
        return MassiveAccessDecision(
            MassiveAccessMode.DISABLED, "missing_credential_slot_evidence"
        )
    if evidence.requested_mode is MassiveAccessMode.DEDICATED:
        if evidence.dedicated_key_confirmed:
            return MassiveAccessDecision(
                MassiveAccessMode.DEDICATED, "dedicated_confirmed"
            )
        return MassiveAccessDecision(
            MassiveAccessMode.DISABLED, "dedicated_key_not_confirmed"
        )
    if host_lease_verified:
        return MassiveAccessDecision(
            MassiveAccessMode.HOST_COORDINATED, "shared_coordinator_confirmed"
        )
    return MassiveAccessDecision(
        MassiveAccessMode.DISABLED, "all_same_key_consumers_not_coordinated"
    )


class AccessDisabled(Exception):
    pass


class RequestBudgetExceeded(Exception):
    pass


class MassiveRequestBudget:
    """Counts upstream requests across one complete Opportunity cycle."""

    def __init__(self, maximum: int) -> None:
        if not 2 <= maximum <= 20:
            raise ValueError("Massive request budget must be between 2 and 20")
        self.maximum = maximum
        self._cycle_id: str | None = None
        self._used = 0
        self._lock = threading.Lock()

    def reset(self, cycle_id: str) -> None:
        if not cycle_id or len(cycle_id) > 128:
            raise ValueError("Massive request budget requires a bounded cycle ID")
        with self._lock:
            if self._cycle_id != cycle_id:
                self._cycle_id = cycle_id
                self._used = 0

    def consume(self) -> None:
        with self._lock:
            if self._cycle_id is None:
                raise RequestBudgetExceeded("request budget cycle is not active")
            if self._used >= self.maximum:
                raise RequestBudgetExceeded("request budget exhausted")
            self._used += 1

    def snapshot(self) -> tuple[str | None, int, int]:
        with self._lock:
            return self._cycle_id, self._used, self.maximum


class MassiveTransport(Protocol):
    def fetch(
        self, dataset: MassiveDataset, symbols: tuple[str, ...]
    ) -> Iterable[SourceEnvelope]: ...

    def fetch_option_chain(
        self, query: OptionChainQuery
    ) -> Iterable[SourceEnvelope]: ...

    def fetch_option_snapshot(
        self, underlying_symbol: str, contract_symbol: str
    ) -> SourceEnvelope: ...


class MassiveAccessCoordinator:
    def __init__(
        self,
        evidence: MassiveAccessEvidence | None = None,
        cooldown: Cooldown | None = None,
        lease_store: HostLeaseStore | None = None,
        lease: HostLease | None = None,
    ) -> None:
        selected = evidence or MassiveAccessEvidence()
        verified = False
        if (
            selected.requested_mode is MassiveAccessMode.HOST_COORDINATED
            and lease_store is not None
            and lease is not None
            and selected.credential_slot_id == lease.credential_slot_id
        ):
            try:
                lease_store.assert_owned(lease)
                verified = True
            except HostLeaseError:
                verified = False
        self.decision = decide_access(selected, host_lease_verified=verified)
        self.cooldown = cooldown or Cooldown()
        self.lease_store = lease_store
        self.lease = lease
        slot = selected.credential_slot_id or "disabled"
        with _HOST_ADMISSIONS_LOCK:
            self._shared_admission = _HOST_ADMISSIONS.setdefault(
                slot, threading.BoundedSemaphore(value=1)
            )

    @contextmanager
    def admission(self):
        if self.decision.mode is MassiveAccessMode.DISABLED:
            raise AccessDisabled(self.decision.reason)
        host_coordinated = self.decision.mode is MassiveAccessMode.HOST_COORDINATED
        self._shared_admission.acquire()
        try:
            if host_coordinated:
                if self.lease_store is None or self.lease is None:
                    raise AccessDisabled("shared_coordinator_unavailable")
                try:
                    self.lease_store.assert_owned(self.lease)
                    host_remaining = self.lease_store.cooldown_remaining(self.lease)
                except HostLeaseError as error:
                    raise AccessDisabled("shared_coordinator_unavailable") from error
                if host_remaining > 0:
                    raise RateLimited(host_remaining)
            remaining = self.cooldown.remaining()
            if remaining > 0:
                raise RateLimited(remaining)
            yield
        finally:
            self._shared_admission.release()

    def record_rate_limit(self, retry_after: float) -> None:
        self.cooldown.record(retry_after)
        if self.decision.mode is MassiveAccessMode.HOST_COORDINATED:
            if self.lease_store is None or self.lease is None:
                raise AccessDisabled("shared_coordinator_unavailable")
            try:
                self.lease_store.record_cooldown(self.lease, retry_after)
            except HostLeaseError as error:
                raise AccessDisabled("shared_coordinator_unavailable") from error


@dataclass(frozen=True)
class MassiveResult:
    access_mode: MassiveAccessMode
    posture: str
    reason: str
    inserted: int = 0
    duplicates: int = 0
    retry_after: float | None = None


@dataclass(frozen=True)
class MassiveCapture:
    result: MassiveResult
    records: tuple[CapturedMassiveRecord, ...] = ()


def _small_universe(symbols: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(symbol.strip().upper() for symbol in symbols))
    if not normalized or len(normalized) > 50:
        raise ValueError("Massive universe must contain 1..50 symbols")
    if any(not symbol or symbol == "*" for symbol in normalized):
        raise ValueError("Massive full-market or empty symbols are forbidden")
    if any(
        not symbol.replace(".", "").replace("-", "").isalnum() for symbol in normalized
    ):
        raise ValueError("Massive symbols must be explicit ticker identifiers")
    return normalized


class MassiveRestAdapter:
    def __init__(
        self,
        transport: MassiveTransport,
        raw_store: RawSink,
        coordinator: MassiveAccessCoordinator,
        request_budget: MassiveRequestBudget | None = None,
    ) -> None:
        self.transport = transport
        self.raw_store = raw_store
        self.coordinator = coordinator
        self.request_budget = request_budget

    def reset_budget(self, cycle_id: str) -> None:
        if self.request_budget is not None:
            self.request_budget.reset(cycle_id)

    def _consume_request(self) -> None:
        if self.request_budget is not None:
            self.request_budget.consume()

    def _capture_many(
        self,
        fetcher: Callable[[], Iterable[SourceEnvelope]],
        *,
        healthy_reason: str,
        invalid_envelope_message: str,
    ) -> MassiveCapture:
        records: list[CapturedMassiveRecord] = []
        inserted = 0
        duplicates = 0
        try:
            with self.coordinator.admission():
                self._consume_request()
                try:
                    for envelope in fetcher():
                        if (
                            envelope.source_id != "massive"
                            or envelope.channel != "rest"
                        ):
                            raise ValueError(invalid_envelope_message)
                        receipt = self.raw_store.save(envelope)
                        inserted += int(receipt.inserted)
                        duplicates += int(not receipt.inserted)
                        records.append(
                            CapturedMassiveRecord(
                                envelope=envelope,
                                raw_id=receipt.id,
                                raw_version=1,
                                content_hash=receipt.content_hash,
                                known_at=receipt.known_at,
                            )
                        )
                except RateLimited as error:
                    self.coordinator.record_rate_limit(error.retry_after)
                    return self._capture_result(
                        posture="rate_limited",
                        reason="upstream_429",
                        inserted=inserted,
                        duplicates=duplicates,
                        records=records,
                        retry_after=error.retry_after,
                    )
            return self._capture_result(
                posture="healthy",
                reason=healthy_reason,
                inserted=inserted,
                duplicates=duplicates,
                records=records,
            )
        except (AccessDisabled, RequestBudgetExceeded, RateLimited) as error:
            return self._unavailable_capture(error)

    def _capture_result(
        self,
        *,
        posture: str,
        reason: str,
        inserted: int = 0,
        duplicates: int = 0,
        records: Sequence[CapturedMassiveRecord] = (),
        retry_after: float | None = None,
        access_mode: MassiveAccessMode | None = None,
    ) -> MassiveCapture:
        return MassiveCapture(
            result=MassiveResult(
                access_mode=access_mode or self.coordinator.decision.mode,
                posture=posture,
                reason=reason,
                inserted=inserted,
                duplicates=duplicates,
                retry_after=retry_after,
            ),
            records=tuple(records),
        )

    def _unavailable_capture(
        self, error: AccessDisabled | RequestBudgetExceeded | RateLimited
    ) -> MassiveCapture:
        if isinstance(error, AccessDisabled):
            return self._capture_result(
                posture="disabled",
                reason=str(error),
                access_mode=MassiveAccessMode.DISABLED,
            )
        if isinstance(error, RequestBudgetExceeded):
            return self._capture_result(
                posture="budget_exhausted",
                reason="cycle_request_budget_exhausted",
            )
        return self._capture_result(
            posture="rate_limited",
            reason="retry_after_cooldown",
            retry_after=error.retry_after,
        )

    def fetch(self, dataset: MassiveDataset, symbols: Sequence[str]) -> MassiveResult:
        return self.capture(dataset, symbols).result

    def capture(
        self, dataset: MassiveDataset, symbols: Sequence[str]
    ) -> MassiveCapture:
        universe = _small_universe(symbols)
        return self._capture_many(
            lambda: self.transport.fetch(dataset, universe),
            healthy_reason="bounded_rest",
            invalid_envelope_message=(
                "Massive REST adapter received an invalid source envelope"
            ),
        )

    def capture_option_chain(self, query: OptionChainQuery) -> MassiveCapture:
        universe = _small_universe((query.underlying_symbol,))
        normalized = OptionChainQuery(
            underlying_symbol=universe[0],
            contract_type=query.contract_type,
            expiration_from=query.expiration_from,
            expiration_to=query.expiration_to,
            strike_from=query.strike_from,
            strike_to=query.strike_to,
        )
        if normalized.contract_type not in ("call", "put"):
            raise ValueError("Massive option contract_type must be call or put")
        if (
            normalized.strike_from is not None
            and normalized.strike_to is not None
            and (
                normalized.strike_from <= 0
                or normalized.strike_to <= normalized.strike_from
            )
        ):
            raise ValueError("Massive option strike range is invalid")
        return self._capture_many(
            lambda: self.transport.fetch_option_chain(normalized),
            healthy_reason="on_demand_option_chain",
            invalid_envelope_message=(
                "Massive option adapter received an invalid source envelope"
            ),
        )

    def capture_option_snapshot(
        self, underlying_symbol: str, contract_symbol: str
    ) -> MassiveCapture:
        underlying = _small_universe((underlying_symbol,))[0]
        contract = contract_symbol.strip().upper()
        if (
            not contract
            or len(contract) > 32
            or not contract.replace(".", "").replace("-", "").replace(":", "").isalnum()
        ):
            raise ValueError("Massive option contract symbol is invalid")
        return self._capture_many(
            lambda: (self.transport.fetch_option_snapshot(underlying, contract),),
            healthy_reason="exact_option_snapshot",
            invalid_envelope_message=(
                "Massive option adapter received an invalid source envelope"
            ),
        )
