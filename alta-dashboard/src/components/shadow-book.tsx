import {
  ChartNoAxesCombined,
  CircleDot,
  ShieldCheck,
  Waypoints,
} from "lucide-react";
import { StatusPill } from "@/components/status-pill";
import { useI18n } from "@/lib/i18n";
import type { MvpStatus, RuntimeDetail, SelectedEntity } from "@/lib/types";
import { cn } from "@/lib/utils";

function finiteValue(value: string | number | null | undefined) {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

type FormatNumber = (
  value?: number,
  options?: Intl.NumberFormatOptions,
) => string;

function bps(
  value: string | number | null | undefined,
  formatNumber: FormatNumber,
) {
  const parsed = finiteValue(value);
  if (parsed === null) return "—";
  return `${parsed > 0 ? "+" : ""}${formatNumber(parsed, {
    maximumFractionDigits: 1,
  })} bps`;
}

function magnitudeBps(
  value: string | number | null | undefined,
  formatNumber: FormatNumber,
) {
  const parsed = finiteValue(value);
  if (parsed === null) return "—";
  return `${formatNumber(parsed, {
    maximumFractionDigits: 1,
  })} bps`;
}

function rate(
  value: string | number | null | undefined,
  formatNumber: FormatNumber,
) {
  const parsed = finiteValue(value);
  if (parsed === null) return "—";
  return `${formatNumber(parsed * 100, {
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
  const {
    domain,
    number: formatNumber,
    relative,
    systemMessage,
    t,
  } = useI18n();
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
      ? `${bps(evidence.confidence95LowerBps, formatNumber)} – ${bps(
          evidence.confidence95UpperBps,
          formatNumber,
        )}`
      : t("awaitingIndependentCloses");

  return (
    <section className="shadow-book">
      <div className="shadow-warning">
        <ShieldCheck />
        <div>
          <strong>{t("observationNotBrokerage")}</strong>
          <p>{t("observationNotBrokerageDetail")}</p>
        </div>
      </div>
      <div className="alpha-evidence">
        <header className="alpha-evidence-head">
          <div>
            <h2>{t("forwardAlphaEvidence")}</h2>
            <p>{t("forwardAlphaDetail")}</p>
          </div>
          <span className={cn("alpha-posture", postureTone)}>
            <CircleDot />
            {domain(posture)}
          </span>
        </header>
        <div className="alpha-evidence-grid">
          <div className="alpha-measure is-sample">
            <span>{t("comparableCloses")}</span>
            <strong>
              {formatNumber(sampleSize)}
              <small> / {t("minimum", { count: minimumSample })}</small>
            </strong>
            <p>
              {sampleSize < minimumSample
                ? t("moreBeforeCalibration", {
                    count: minimumSample - sampleSize,
                  })
                : t("calibrationReached")}
            </p>
          </div>
          <div className="alpha-measure">
            <span>{t("meanRealizedAlpha")}</span>
            <strong>{bps(alpha?.meanRealizedAlphaBps, formatNumber)}</strong>
            <p>{interval}</p>
          </div>
          <div className="alpha-measure">
            <span>{t("forecastMae")}</span>
            <strong>
              {magnitudeBps(calibration?.meanAbsoluteErrorBps, formatNumber)}
            </strong>
            <p>{t("forecastMaeDetail")}</p>
          </div>
          <div className="alpha-measure">
            <span>{t("directionalHitRate")}</span>
            <strong>
              {rate(calibration?.directionalHitRate, formatNumber)}
            </strong>
            <p>{t("directionalHitDetail")}</p>
          </div>
          <div className="alpha-measure">
            <span>{t("forecastReserve")}</span>
            <strong>
              {magnitudeBps(calibration?.alphaReserveBps, formatNumber)}
            </strong>
            <p>
              {calibration?.posture === "collecting"
                ? t("forecastReserveInactive")
                : t("forecastReserveActive")}
            </p>
          </div>
          <div className="alpha-measure">
            <span>{t("capitalPosture")}</span>
            <strong>
              {effectiveCapital === null
                ? "—"
                : `${formatNumber(effectiveCapital, {
                    maximumFractionDigits: 2,
                  })}×`}
            </strong>
            <p>{t("capitalPostureDetail")}</p>
          </div>
        </div>
        <section
          className="path-diagnostics"
          aria-labelledby="path-quality-title"
        >
          <header>
            <div>
              <h3 id="path-quality-title">{t("observedLifecycleQuality")}</h3>
              <p>{t("observedLifecycleDetail")}</p>
            </div>
            <span>
              {t("measured", {
                count: formatNumber(path?.measuredPositions ?? 0),
              })}
            </span>
          </header>
          <div className="path-diagnostics-grid">
            <div>
              <span>{t("meanFavorableExcursion")}</span>
              <strong>
                {magnitudeBps(
                  path?.meanMaximumFavorableExcursionBps,
                  formatNumber,
                )}
              </strong>
            </div>
            <div>
              <span>{t("meanAdverseExcursion")}</span>
              <strong>
                {bps(path?.meanMaximumAdverseExcursionBps, formatNumber)}
              </strong>
            </div>
            <div>
              <span>{t("meanExitCapture")}</span>
              <strong>{rate(path?.meanExitCaptureRatio, formatNumber)}</strong>
            </div>
            <div>
              <span>{t("positivePathMissed")}</span>
              <strong>
                {rate(path?.positiveExcursionMissRate, formatNumber)}
              </strong>
            </div>
          </div>
        </section>
        <footer className="alpha-evidence-foot">
          <ChartNoAxesCombined />
          <span>{systemMessage(alpha?.warning) ?? t("noClosedSample")}</span>
          <small>
            {t("lastMeasured", {
              time: relative(alpha?.lastMeasuredAt ?? undefined),
            })}
          </small>
        </footer>
      </div>
      <div className="shadow-table">
        <div className="shadow-row is-head">
          <span>{t("instrument")}</span>
          <span>{t("status")}</span>
          <span>{t("quantity")}</span>
          <span>{t("opened")}</span>
          <span>{t("expression")}</span>
        </div>
        {status.shadowPositions.map((position) => (
          <button
            className="shadow-row"
            key={position.id}
            onClick={() =>
              onSelect({
                kind: "position",
                id: position.id,
                label: t("shadowPosition", { symbol: position.symbol }),
                summary: position as unknown as Record<string, unknown>,
              })
            }
          >
            <strong>{position.symbol}</strong>
            <StatusPill status={position.status} />
            <span>{position.quantity ?? "—"}</span>
            <span>{relative(position.openedAt)}</span>
            <span>{position.expressionId}</span>
          </button>
        ))}
        {!status.shadowPositions.length && (
          <div className="shadow-empty">
            <Waypoints />
            <p>{t("noShadowPositions")}</p>
          </div>
        )}
      </div>
    </section>
  );
}
