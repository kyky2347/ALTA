from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable

from .alpha_isolation import (
    AlphaSource,
    SystematicExposure,
    normalize_alpha_source,
    normalize_systematic_exposure,
)
from .database import Database
from .implementation import (
    AlphaSourceBucket,
    CatalystBucket,
    ExposureBucket,
    PortfolioState,
)
from .opportunity_identity import normalize_catalyst_bucket


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
                o.catalyst_key
            FROM research.shadow_position p
            LEFT JOIN research.opportunity o
              ON o.id = p.position_thesis->'binding'->>'opportunity_id'
             AND o.environment = p.environment
            WHERE p.environment = 'shadow' AND {position_filter}
            ORDER BY p.opened_at, p.id""",
            parameters,
        ).fetchall()
    return project_portfolio_state(rows, max_open_positions=max_open_positions)


def project_portfolio_state(
    rows: Iterable[tuple[Decimal, Any, str | None]], *, max_open_positions: int
) -> PortfolioState:
    """Projects durable position rows without granting favorable legacy assumptions."""

    notionals: list[Decimal] = []
    stress_losses: list[Decimal] = []
    exposure_totals: dict[SystematicExposure, Decimal] = {}
    source_totals: dict[AlphaSource, tuple[int, Decimal, Decimal]] = {}
    catalyst_totals: dict[str, tuple[int, Decimal, Decimal]] = {}
    for raw_notional, raw_thesis, raw_catalyst_key in rows:
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
    )


def _scaled_stress_loss(
    notional: Decimal, implementation: dict[str, Any] | None
) -> Decimal:
    if implementation is None:
        return Decimal(0)
    entry_notional = Decimal(str(implementation.get("target_notional", "0")))
    entry_stress_loss = Decimal(str(implementation.get("estimated_stress_loss", "0")))
    if entry_notional <= 0 or entry_stress_loss <= 0:
        return Decimal(0)
    return entry_stress_loss * notional / entry_notional


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
