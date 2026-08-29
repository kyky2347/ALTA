import {
  ChartNoAxesCombined,
  CircleDot,
  ShieldCheck,
  Waypoints,
} from "lucide-react";
import { StatusPill } from "@/components/status-pill";
import { relativeTime, titleCase } from "@/lib/display";
import type { MvpStatus, RuntimeDetail, SelectedEntity } from "@/lib/types";
import { cn } from "@/lib/utils";

function finiteValue(value: string | number | null | undefined) {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function bps(value: string | number | null | undefined) {
  const parsed = finiteValue(value);
  if (parsed === null) return "—";
  return `${parsed > 0 ? "+" : ""}${parsed.toLocaleString(undefined, {
    maximumFractionDigits: 1,
  })} bps`;
}

function magnitudeBps(value: string | number | null | undefined) {
  const parsed = finiteValue(value);
  if (parsed === null) return "—";
  return `${parsed.toLocaleString(undefined, {
    maximumFractionDigits: 1,
  })} bps`;
}

function rate(value: string | number | null | undefined) {
  const parsed = finiteValue(value);
  if (parsed === null) return "—";
  return `${(parsed * 100).toLocaleString(undefined, {
    maximumFractionDigits: 1,
  })}%`;
}

export function ShadowBook({
  status,
  runtime,
  onSelect,
}: {
  status: MvpStatus;
  runtime: RuntimeDetail | null;
  onSelect: (entity: SelectedEntity) => void;
}) {
  const alpha = runtime?.alpha;
  const evidence = alpha?.alphaEvidence;
  const calibration = alpha?.forecastCalibrationGovernance;
  const capital = alpha?.capitalGovernance;
  const path = alpha?.pathDiagnostics;
  const sampleSize = evidence?.sampleSize ?? alpha?.closedPositions ?? 0;
  const minimumSample =
    evidence?.minimumSample ?? calibration?.minimumSample ?? 30;
  const posture = capital?.posture ?? evidence?.posture ?? "not measured";
  const postureTone = ["preservation", "probation", "caution", "negative"].some(
    (value) => posture.includes(value),
  )
    ? "is-caution"
    : ["collecting", "insufficient", "not measured"].some((value) =>
          posture.includes(value),
        )
      ? "is-collecting"
      : "is-normal";
  const capitalMultipliers = [
    finiteValue(capital?.capitalMultiplier),
    finiteValue(calibration?.capitalMultiplier),
  ].filter((value): value is number => value !== null);
  const effectiveCapital = capitalMultipliers.length
    ? Math.min(...capitalMultipliers)
    : null;
  const interval =
    evidence?.confidence95LowerBps != null &&
    evidence?.confidence95UpperBps != null
      ? `${bps(evidence.confidence95LowerBps)} to ${bps(
          evidence.confidence95UpperBps,
        )}`
      : "Awaiting enough independent closes";

  return (
    <section className="shadow-book">
      <div className="shadow-warning">
        <ShieldCheck />
        <div>
          <strong>Observation, not brokerage</strong>
          <p>
            Every row is a research shadow position. This dashboard exposes no
            capital or live-order path.
          </p>
        </div>
      </div>
      <div className="alpha-evidence">
        <header className="alpha-evidence-head">
          <div>
            <h2>Forward Alpha evidence</h2>
            <p>
              Cost-adjusted Shadow outcomes relative to SPY, measured from
              entry-frozen decisions. This is an evidence ledger, not a
              performance claim.
            </p>
          </div>
          <span className={cn("alpha-posture", postureTone)}>
            <CircleDot />
            {titleCase(posture)}
          </span>
        </header>
        <div className="alpha-evidence-grid">
          <div className="alpha-measure is-sample">
            <span>Comparable closes</span>
            <strong>
              {sampleSize.toLocaleString()}
              <small> / {minimumSample} minimum</small>
            </strong>
            <p>
              {sampleSize < minimumSample
                ? `${minimumSample - sampleSize} more before calibration can affect forecasts.`
                : "Minimum calibration sample reached; rolling evidence now governs forecasts."}
            </p>
          </div>
          <div className="alpha-measure">
            <span>Mean realized Alpha</span>
            <strong>{bps(alpha?.meanRealizedAlphaBps)}</strong>
            <p>{interval}</p>
          </div>
          <div className="alpha-measure">
            <span>Forecast MAE</span>
            <strong>{magnitudeBps(calibration?.meanAbsoluteErrorBps)}</strong>
            <p>Absolute error on comparable direct-stock forecasts.</p>
          </div>
          <div className="alpha-measure">
            <span>Directional hit rate</span>
            <strong>{rate(calibration?.directionalHitRate)}</strong>
            <p>Descriptive only; zero forecasts and outcomes are excluded.</p>
          </div>
          <div className="alpha-measure">
            <span>Forecast reserve</span>
            <strong>{magnitudeBps(calibration?.alphaReserveBps)}</strong>
            <p>
              {calibration?.posture === "collecting"
                ? "Inactive while the sample is immature."
                : "Deducted from new expected Alpha before costs."}
            </p>
          </div>
          <div className="alpha-measure">
            <span>Capital posture</span>
            <strong>
              {effectiveCapital === null
                ? "—"
                : `${effectiveCapital.toLocaleString(undefined, {
                    maximumFractionDigits: 2,
                  })}×`}
            </strong>
            <p>
              The tightest forward-evidence multiplier; it can never add
              leverage.
            </p>
          </div>
        </div>
        <section
          className="path-diagnostics"
          aria-labelledby="path-quality-title"
        >
          <header>
            <div>
              <h3 id="path-quality-title">Observed lifecycle quality</h3>
              <p>
                Executable exit observations separate opportunity quality from
                path risk and exit capture. They never create an automatic exit.
              </p>
            </div>
            <span>
              {(path?.measuredPositions ?? 0).toLocaleString()} measured
            </span>
          </header>
          <div className="path-diagnostics-grid">
            <div>
              <span>Mean favorable excursion</span>
              <strong>
                {magnitudeBps(path?.meanMaximumFavorableExcursionBps)}
              </strong>
            </div>
            <div>
              <span>Mean adverse excursion</span>
              <strong>{bps(path?.meanMaximumAdverseExcursionBps)}</strong>
            </div>
            <div>
              <span>Mean exit capture</span>
              <strong>{rate(path?.meanExitCaptureRatio)}</strong>
            </div>
            <div>
              <span>Positive path missed</span>
              <strong>{rate(path?.positiveExcursionMissRate)}</strong>
            </div>
          </div>
        </section>
        <footer className="alpha-evidence-foot">
          <ChartNoAxesCombined />
          <span>
            {alpha?.warning ??
              "No closed, benchmarked Shadow sample is available yet."}
          </span>
          <small>
            Last measured {relativeTime(alpha?.lastMeasuredAt ?? undefined)}
          </small>
        </footer>
      </div>
      <div className="shadow-table">
        <div className="shadow-row is-head">
          <span>Instrument</span>
          <span>Status</span>
          <span>Quantity</span>
          <span>Opened</span>
          <span>Expression</span>
        </div>
        {status.shadowPositions.map((position) => (
          <button
            className="shadow-row"
            key={position.id}
            onClick={() =>
              onSelect({
                kind: "position",
                id: position.id,
                label: `${position.symbol} shadow position`,
                summary: position as unknown as Record<string, unknown>,
              })
            }
          >
            <strong>{position.symbol}</strong>
            <StatusPill status={position.status} />
            <span>{position.quantity ?? "—"}</span>
            <span>{relativeTime(position.openedAt)}</span>
            <span>{position.expressionId}</span>
          </button>
        ))}
        {!status.shadowPositions.length && (
          <div className="shadow-empty">
            <Waypoints />
            <p>No shadow positions are open or recently closed.</p>
          </div>
        )}
      </div>
    </section>
  );
}
