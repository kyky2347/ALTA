import {
  Activity,
  Bot,
  Database,
  FileSearch2,
  Radar,
  ShieldCheck,
  Waypoints,
} from "lucide-react";
import { StatusPill } from "@/components/status-pill";
import { relativeTime, titleCase } from "@/lib/display";
import type { MvpStatus, RuntimeDetail, SelectedEntity } from "@/lib/types";

export function SystemOverview({
  status,
  runtime,
  onSelect,
}: {
  status: MvpStatus;
  runtime: RuntimeDetail | null;
  onSelect: (entity: SelectedEntity) => void;
}) {
  return (
    <section className="overview-grid">
      <OverviewBlock
        icon={FileSearch2}
        label="Candidates"
        value={status.candidates.length}
        detail="Recent foundry inputs"
      />
      <OverviewBlock
        icon={Radar}
        label="Opportunities"
        value={status.opportunities.length}
        detail="Deduplicated theses"
      />
      <OverviewBlock
        icon={Bot}
        label="Agent roles"
        value={status.agents.length}
        detail={`${runtime?.minds.length ?? 0} persistent minds`}
      />
      <OverviewBlock
        icon={Waypoints}
        label="Expressions"
        value={status.expressions.length}
        detail="Audited carriers"
      />
      <OverviewBlock
        icon={ShieldCheck}
        label="Shadow positions"
        value={status.shadowPositions.length}
        detail="Capital disabled"
      />
      <OverviewBlock
        icon={Database}
        label="Event cursor"
        value={status.eventCursor}
        detail="Append-only ledger"
      />
      <div className="overview-wide">
        <div className="overview-wide-head">
          <span>
            <Activity /> Source posture
          </span>
          <StatusPill status={status.sources.length ? "observed" : "waiting"} />
        </div>
        <div className="source-list">
          {status.sources.slice(0, 5).map((source) => (
            <div key={source.id}>
              <strong>{titleCase(source.id)}</strong>
              <span>
                {titleCase(
                  String(source.posture ?? source.status ?? "recorded"),
                )}
              </span>
              <small>{relativeTime(source.knownAt)}</small>
            </div>
          ))}
          {!status.sources.length && (
            <p>No source posture has been recorded.</p>
          )}
        </div>
      </div>
      <div className="overview-wide">
        <div className="overview-wide-head">
          <span>
            <Bot /> Trader minds
          </span>
          <StatusPill status={`${runtime?.minds.length ?? 0} minds`} />
        </div>
        <div className="mind-list">
          {runtime?.minds.slice(0, 4).map((mind) => (
            <button
              key={mind.id}
              onClick={() =>
                onSelect({
                  kind: "event",
                  id: mind.id,
                  label: titleCase(mind.id),
                  summary: mind as unknown as Record<string, unknown>,
                })
              }
            >
              <strong>{titleCase(mind.id)}</strong>
              <span>{mind.rollingSummary ?? "No rolling summary saved"}</span>
              <small>
                {mind.modelId ?? mind.modelProvider ?? "Model pending"}
              </small>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function OverviewBlock({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: typeof Activity;
  label: string;
  value: number;
  detail: string;
}) {
  return (
    <article className="overview-block">
      <span>
        <Icon />
      </span>
      <div>
        <small>{label}</small>
        <strong>{value.toLocaleString()}</strong>
        <p>{detail}</p>
      </div>
    </article>
  );
}
