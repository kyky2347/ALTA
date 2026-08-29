from contextlib import AbstractContextManager
from decimal import Decimal
from typing import Any, Protocol

from .alpha_governance import (
    AlphaCapitalGovernance,
    AlphaCapitalGovernancePolicy,
    CapitalPerformanceObservation,
    evaluate_alpha_capital_governance,
)
from .forecast_calibration import (
    ForecastCalibrationGovernance,
    ForecastCalibrationObservation,
    ForecastCalibrationPolicy,
    evaluate_forecast_calibration,
)
from .implementation import PortfolioRiskPolicy
from .trade_path_diagnostics import (
    PositionPathDiagnostics,
    summarize_path_diagnostics,
)
from .underwriting_calibration import (
    AlphaPerformanceObservation,
    CalibrationObservation,
    frozen_expected_net_alpha_bps,
    summarize_alpha_evidence,
    summarize_underwriting_calibration,
)


class ReportingDatabase(Protocol):
    """Narrow persistence boundary required by Alpha reporting."""

    def connect(self) -> AbstractContextManager[Any]: ...


def _mean_decimal(values: list[Decimal]) -> str | None:
    if not values:
        return None
    return str(sum(values, Decimal(0)) / Decimal(len(values)))


def _positive_rate(values: list[Decimal]) -> str | None:
    if not values:
        return None
    return str(Decimal(sum(value > 0 for value in values)) / Decimal(len(values)))


def _calibration_observations(
    implementation_rows: list[tuple],
    realized_by_position: dict[str, Decimal],
) -> tuple[CalibrationObservation, ...]:
    observations = []
    for position_id, expression_kind, position_thesis in implementation_rows:
        if expression_kind != "stock" or position_id not in realized_by_position:
            continue
        expected_alpha = frozen_expected_net_alpha_bps(position_thesis)
        if expected_alpha is not None:
            observations.append(
                CalibrationObservation(
                    position_id=position_id,
                    expected_alpha_bps=expected_alpha,
                    realized_alpha_bps=realized_by_position[position_id],
                )
            )
    return tuple(observations)


def _path_diagnostics(rows: list[tuple]) -> tuple[PositionPathDiagnostics, ...]:
    diagnostics = []
    for _, payload, _ in rows:
        raw = payload.get("path_diagnostics") if isinstance(payload, dict) else None
        if not isinstance(raw, dict):
            continue
        try:
            diagnostics.append(PositionPathDiagnostics.model_validate(raw))
        except ValueError:
            continue
    return tuple(diagnostics)


def _capital_governance_payload(value: AlphaCapitalGovernance) -> dict[str, Any]:
    return {
        "policyVersion": value.policy_version,
        "sourcePortfolioPolicyVersion": value.source_portfolio_policy_version,
        "posture": value.posture,
        "capitalMultiplier": str(value.capital_multiplier),
        "sampleSize": value.sample_size,
        "windowSize": value.window_size,
        "recentMeanAlphaBps": (
            str(value.recent_mean_alpha_bps)
            if value.recent_mean_alpha_bps is not None
            else None
        ),
        "confidence95UpperAlphaBps": (
            str(value.confidence95_upper_alpha_bps)
            if value.confidence95_upper_alpha_bps is not None
            else None
        ),
        "maxDrawdownNavBps": str(value.max_drawdown_nav_bps),
        "evidencePosture": value.evidence_posture,
        "observedThrough": value.observed_through,
        "reasonCodes": list(value.reason_codes),
    }


def _forecast_calibration_payload(
    value: ForecastCalibrationGovernance,
) -> dict[str, Any]:
    return {
        "policyVersion": value.policy_version,
        "sourcePortfolioPolicyVersion": value.source_portfolio_policy_version,
        "expressionKind": value.expression_kind,
        "posture": value.posture,
        "capitalMultiplier": str(value.capital_multiplier),
        "sampleSize": value.sample_size,
        "windowSize": value.window_size,
        "minimumSample": value.minimum_sample,
        "meanForecastErrorBps": (
            str(value.mean_forecast_error_bps)
            if value.mean_forecast_error_bps is not None
            else None
        ),
        "meanAbsoluteErrorBps": (
            str(value.mean_absolute_error_bps)
            if value.mean_absolute_error_bps is not None
            else None
        ),
        "directionalHitRate": (
            str(value.directional_hit_rate)
            if value.directional_hit_rate is not None
            else None
        ),
        "alphaReserveBps": str(value.alpha_reserve_bps),
        "observedThrough": value.observed_through,
        "reasonCodes": list(value.reason_codes),
    }


def alpha_summary(database: ReportingDatabase, environment: str) -> dict[str, Any]:
    """Build the public forward-Alpha report from durable Shadow records."""

    with database.connect() as connection:
        rows = connection.execute(
            """SELECT aggregate_id, payload, known_at FROM (
                SELECT DISTINCT ON (aggregate_id)
                    aggregate_id, payload, known_at, sequence
                FROM ops.event
                WHERE environment = %s
                  AND event_type = 'position.performance.measured'
                ORDER BY aggregate_id, sequence DESC
            ) latest ORDER BY sequence""",
            (environment,),
        ).fetchall()
        open_positions = connection.execute(
            """SELECT count(*) FROM research.shadow_position
            WHERE environment = %s AND status = 'open'""",
            (environment,),
        ).fetchone()[0]
        position_ids = [row[0] for row in rows]
        implementation_rows = (
            connection.execute(
                """SELECT p.id, e.kind, p.position_thesis
                FROM research.shadow_position p
                JOIN research.expression e ON e.id = p.expression_id
                WHERE p.id = ANY(%s) AND p.environment = %s
                ORDER BY p.id""",
                (position_ids, environment),
            ).fetchall()
            if position_ids
            else []
        )

    returns = [Decimal(row[1]["net_return_bps"]) for row in rows]
    alphas = [
        Decimal(row[1]["realized_alpha_bps"])
        for row in rows
        if row[1].get("realized_alpha_bps") is not None
    ]
    pnl = [Decimal(row[1]["net_pnl"]) for row in rows]
    realized_by_position = {
        row[0]: Decimal(row[1]["realized_alpha_bps"])
        for row in rows
        if row[1].get("realized_alpha_bps") is not None
    }
    alpha_evidence = summarize_alpha_evidence(
        tuple(
            AlphaPerformanceObservation(
                position_id=row[0],
                realized_alpha_bps=Decimal(row[1]["realized_alpha_bps"]),
            )
            for row in rows
            if row[1].get("realized_alpha_bps") is not None
        )
    )
    portfolio_policy = PortfolioRiskPolicy()
    capital_governance = alpha_capital_governance(
        database,
        environment,
        reference_nav=portfolio_policy.reference_nav,
        source_portfolio_policy_version=portfolio_policy.version,
    )
    forecast_calibration = forecast_calibration_governance(
        database,
        environment,
        source_portfolio_policy_version=portfolio_policy.version,
        expression_kind="stock",
    )
    return {
        "measurement": "realized_shadow_cost_adjusted",
        "closedPositions": len(rows),
        "openPositions": open_positions,
        "positiveReturnRate": _positive_rate(returns),
        "meanNetReturnBps": _mean_decimal(returns),
        "meanRealizedAlphaBps": _mean_decimal(alphas),
        "cumulativeNetPnl": str(sum(pnl, Decimal(0))),
        "lastMeasuredAt": rows[-1][2] if rows else None,
        "alphaEvidence": alpha_evidence,
        "capitalGovernance": _capital_governance_payload(capital_governance),
        "forecastCalibrationGovernance": _forecast_calibration_payload(
            forecast_calibration
        ),
        "pathDiagnostics": summarize_path_diagnostics(_path_diagnostics(rows)),
        "underwritingCalibration": summarize_underwriting_calibration(
            _calibration_observations(implementation_rows, realized_by_position)
        ),
        "warning": alpha_evidence["warning"],
    }


def alpha_capital_governance(
    database: ReportingDatabase,
    environment: str,
    *,
    reference_nav: Decimal,
    source_portfolio_policy_version: str,
    policy: AlphaCapitalGovernancePolicy | None = None,
) -> AlphaCapitalGovernance:
    """Load the bounded rolling capital posture from current-policy outcomes."""

    policy = policy or AlphaCapitalGovernancePolicy()
    with database.connect() as connection:
        rows = connection.execute(
            """WITH latest AS (
                SELECT DISTINCT ON (aggregate_id)
                    aggregate_id, payload, known_at, sequence
                FROM ops.event
                WHERE environment = %s
                  AND event_type = 'position.performance.measured'
                  AND payload->>'cost_adjusted' = 'true'
                  AND payload->>'realized_alpha_bps' IS NOT NULL
                ORDER BY aggregate_id, sequence DESC
            )
            SELECT latest.aggregate_id, latest.known_at, latest.payload,
                   count(*) OVER () AS total_sample_size
            FROM latest
            JOIN research.shadow_position position
              ON position.id = latest.aggregate_id
             AND position.environment = %s
            WHERE position.position_thesis->'implementation_plan'
                  ->>'policy_version' = %s
            ORDER BY latest.sequence DESC
            LIMIT %s""",
            (
                environment,
                environment,
                source_portfolio_policy_version,
                policy.window_size,
            ),
        ).fetchall()
    observations = tuple(
        CapitalPerformanceObservation(
            position_id=row[0],
            known_at=row[1],
            net_pnl=Decimal(row[2]["net_pnl"]),
            realized_alpha_bps=Decimal(row[2]["realized_alpha_bps"]),
        )
        for row in reversed(rows)
    )
    return evaluate_alpha_capital_governance(
        observations,
        reference_nav=reference_nav,
        source_portfolio_policy_version=source_portfolio_policy_version,
        policy=policy,
        total_sample_size=int(rows[0][3]) if rows else 0,
    )


def forecast_calibration_governance(
    database: ReportingDatabase,
    environment: str,
    *,
    source_portfolio_policy_version: str,
    expression_kind: str = "stock",
    policy: ForecastCalibrationPolicy | None = None,
) -> ForecastCalibrationGovernance:
    """Load comparable, forward-only forecast error for new plans."""

    policy = policy or ForecastCalibrationPolicy()
    if expression_kind != "stock":
        return ForecastCalibrationGovernance.unscoped(
            source_portfolio_policy_version,
            expression_kind,
        )
    with database.connect() as connection:
        rows = connection.execute(
            """WITH latest AS (
                SELECT DISTINCT ON (aggregate_id)
                    aggregate_id, payload, known_at, sequence
                FROM ops.event
                WHERE environment = %s
                  AND event_type = 'position.performance.measured'
                  AND payload->>'cost_adjusted' = 'true'
                  AND payload->>'realized_alpha_bps' IS NOT NULL
                ORDER BY aggregate_id, sequence DESC
            )
            SELECT latest.aggregate_id, latest.known_at, latest.payload,
                   position.position_thesis,
                   count(*) OVER () AS total_sample_size
            FROM latest
            JOIN research.shadow_position position
              ON position.id = latest.aggregate_id
             AND position.environment = %s
            JOIN research.expression expression
              ON expression.id = position.expression_id
             AND expression.environment = position.environment
            WHERE expression.kind = %s
              AND position.position_thesis->'implementation_plan'
                  ->>'policy_version' = %s
              AND COALESCE(
                  position.position_thesis->'implementation_plan'
                      ->'alpha_clock'
                      ->>'time_adjusted_expected_net_alpha_bps',
                  position.position_thesis->'implementation_plan'
                      ->>'expected_net_alpha_bps'
              ) IS NOT NULL
            ORDER BY latest.sequence DESC
            LIMIT %s""",
            (
                environment,
                environment,
                expression_kind,
                source_portfolio_policy_version,
                policy.window_size,
            ),
        ).fetchall()
    observations = []
    for position_id, known_at, performance, thesis, _total in reversed(rows):
        expected = frozen_expected_net_alpha_bps(thesis)
        if expected is None:
            continue
        observations.append(
            ForecastCalibrationObservation(
                position_id=position_id,
                known_at=known_at,
                expected_alpha_bps=expected,
                realized_alpha_bps=Decimal(performance["realized_alpha_bps"]),
            )
        )
    return evaluate_forecast_calibration(
        tuple(observations),
        source_portfolio_policy_version=source_portfolio_policy_version,
        expression_kind=expression_kind,
        policy=policy,
        total_sample_size=int(rows[0][4]) if rows else 0,
    )
