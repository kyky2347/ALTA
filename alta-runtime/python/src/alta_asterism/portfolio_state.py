from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Iterable

from .alpha_isolation import (
    AlphaSource,
    SystematicExposure,
    normalize_alpha_source,
    normalize_systematic_exposure,
)
from .implementation import (
    AlphaSourceBucket,
    CatalystBucket,
    ExposureBucket,
    PortfolioState,
    UnderlyingBucket,
)
from .opportunity_identity import normalize_catalyst_bucket

if TYPE_CHECKING:
    from .database import Database

PortfolioPositionRow = tuple[Decimal, Any, str | None, str, str, Any]
_UNDERLYING_PATTERN = re.compile(r"^[A-Z][A-Z0-9.:-]{0,31}$")


def load_portfolio_state(
    database: Database,
    *,
    max_open_positions: int,
    known_at: datetime | None = None,
) -> PortfolioState:
    """Loads the current or point-in-time Shadow book into a typed risk projection."""

    quote_cutoff = "" if known_at is None else "AND event.known_at <= %s"
    position_filter = (
        "p.status = 'open'"
        if known_at is None
        else "p.opened_at <= %s AND (p.closed_at IS NULL OR p.closed_at > %s)"
    )
    parameters: tuple[datetime, ...] = ()
    if known_at is not None:
        parameters = (known_at, known_at, known_at)
    with database.connect() as connection:
        rows = connection.execute(
            f"""SELECT GREATEST(
                    p.entry_price,
                    COALESCE(
                        (SELECT (event.payload->'observation'->'quote'->>'ask')::numeric
                         FROM ops.event event
                         WHERE event.aggregate_id = p.id
                           AND event.environment = 'shadow'
                           AND event.event_type = 'position.monitored'
                           {quote_cutoff}
                         ORDER BY event.sequence DESC LIMIT 1),
                        p.entry_price
                    )
                ) * p.quantity,
                p.position_thesis,
                o.catalyst_key,
                p.symbol,
                expression.kind,
                expression.rationale
            FROM research.shadow_position p
            JOIN research.expression expression
              ON expression.id = p.expression_id
             AND expression.environment = p.environment
            LEFT JOIN research.opportunity o
              ON o.id = p.position_thesis->'binding'->>'opportunity_id'
             AND o.environment = p.environment
            WHERE p.environment = 'shadow' AND {position_filter}
            ORDER BY p.opened_at, p.id""",
            parameters,
        ).fetchall()
    return project_portfolio_state(rows, max_open_positions=max_open_positions)


def project_portfolio_state(
    rows: Iterable[PortfolioPositionRow], *, max_open_positions: int
) -> PortfolioState:
    """Projects durable position rows without granting favorable legacy assumptions."""

    notionals: list[Decimal] = []
    stress_losses: list[Decimal] = []
    exposure_totals: dict[SystematicExposure, Decimal] = {}
    source_totals: dict[AlphaSource, tuple[int, Decimal, Decimal]] = {}
    catalyst_totals: dict[str, tuple[int, Decimal, Decimal]] = {}
    underlying_totals: dict[str, tuple[int, Decimal, Decimal]] = {}
    for (
        raw_notional,
        raw_thesis,
        raw_catalyst_key,
        symbol,
        expression_kind,
        rationale,
    ) in rows:
        notional = Decimal(raw_notional)
        notionals.append(notional)
        implementation = (
            raw_thesis.get("implementation_plan")
            if isinstance(raw_thesis, dict)
            else None
        )
        alpha_source = normalize_alpha_source(
            implementation.get("alpha_source")
            if isinstance(implementation, dict)
            else None
        )
        stress_loss = _scaled_stress_loss(notional, implementation)
        stress_losses.append(stress_loss)
        count, gross, source_stress = source_totals.get(
            alpha_source, (0, Decimal(0), Decimal(0))
        )
        source_totals[alpha_source] = (
            count + 1,
            gross + notional,
            source_stress + stress_loss,
        )
        catalyst_key = normalize_catalyst_bucket(raw_catalyst_key)
        catalyst_count, catalyst_gross, catalyst_stress = catalyst_totals.get(
            catalyst_key, (0, Decimal(0), Decimal(0))
        )
        catalyst_totals[catalyst_key] = (
            catalyst_count + 1,
            catalyst_gross + notional,
            catalyst_stress + stress_loss,
        )
        underlying_key = _underlying_key(symbol, expression_kind, rationale)
        underlying_count, underlying_gross, underlying_stress = underlying_totals.get(
            underlying_key, (0, Decimal(0), Decimal(0))
        )
        underlying_totals[underlying_key] = (
            underlying_count + 1,
            underlying_gross + notional,
            underlying_stress + stress_loss,
        )
        for exposure in _systematic_exposures(implementation):
            exposure_totals[exposure] = (
                exposure_totals.get(exposure, Decimal(0)) + notional
            )

    full_book = len(notionals) >= max_open_positions
    return PortfolioState(
        known_open_positions=len(notionals),
        gross_notional=sum(notionals, Decimal(0)),
        prospective_replacement_credit=(
            min(notionals) if full_book and notionals else Decimal(0)
        ),
        aggregate_stress_loss=sum(stress_losses, Decimal(0)),
        prospective_replacement_stress_credit=(
            min(stress_losses) if full_book and stress_losses else Decimal(0)
        ),
        exposure_buckets=tuple(
            ExposureBucket(tag=tag, gross_notional=value)
            for tag, value in sorted(exposure_totals.items())
        ),
        alpha_source_buckets=tuple(
            AlphaSourceBucket(
                source=source,
                open_positions=values[0],
                gross_notional=values[1],
                estimated_stress_loss=values[2],
            )
            for source, values in sorted(source_totals.items())
        ),
        catalyst_buckets=tuple(
            CatalystBucket(
                catalyst_key=catalyst_key,
                open_positions=values[0],
                gross_notional=values[1],
                estimated_stress_loss=values[2],
            )
            for catalyst_key, values in sorted(catalyst_totals.items())
        ),
        underlying_buckets=tuple(
            UnderlyingBucket(
                underlying_key=underlying_key,
                open_positions=values[0],
                gross_notional=values[1],
                estimated_stress_loss=values[2],
            )
            for underlying_key, values in sorted(underlying_totals.items())
        ),
    )


def normalize_underlying_key(value: object) -> str:
    normalized = str(value or "").strip().upper()
    return normalized if _UNDERLYING_PATTERN.fullmatch(normalized) else "UNKNOWN"


def _underlying_key(symbol: str, expression_kind: str, rationale: Any) -> str:
    payload = rationale
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = None
    market_instrument = (
        payload.get("market_instrument") if isinstance(payload, dict) else None
    )
    underlying = (
        market_instrument.get("underlying_symbol")
        if isinstance(market_instrument, dict)
        else None
    )
    if underlying is not None:
        return normalize_underlying_key(underlying)
    if expression_kind == "option":
        return "UNKNOWN"
    return normalize_underlying_key(symbol)


def _scaled_stress_loss(
    notional: Decimal, implementation: dict[str, Any] | None
) -> Decimal:
    if implementation is None:
        return notional
    try:
        entry_notional = Decimal(str(implementation.get("target_notional", "0")))
        entry_stress_loss = Decimal(
            str(implementation.get("estimated_stress_loss", "0"))
        )
    except (ArithmeticError, TypeError, ValueError):
        return notional
    if entry_notional <= 0 or entry_stress_loss <= 0:
        return notional
    scaled = entry_stress_loss * notional / entry_notional
    return min(notional, max(Decimal(0), scaled))


def _systematic_exposures(
    implementation: dict[str, Any] | None,
) -> tuple[SystematicExposure, ...]:
    raw_exposures = (
        implementation.get("systematic_exposures", ())
        if implementation is not None
        else ("unknown",)
    )
    exposures = (
        raw_exposures if isinstance(raw_exposures, (list, tuple)) else ("unknown",)
    )
    return tuple(
        dict.fromkeys(
            normalize_systematic_exposure(item) for item in (exposures or ("unknown",))
        )
    )
