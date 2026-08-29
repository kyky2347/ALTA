import {
  Bot,
  CalendarClock,
  CheckCircle2,
  CircleDot,
  FileSearch2,
  ShieldCheck,
  Sparkles,
  Waypoints,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { StatusPill } from "@/components/status-pill";
import { useI18n } from "@/lib/i18n";
import type { AltaEvent, MvpStatus, SelectedEntity } from "@/lib/types";
import { cn } from "@/lib/utils";

function iconFor(event: AltaEvent) {
  if (event.eventType.startsWith("candidate")) return FileSearch2;
  if (event.eventType.startsWith("opportunity")) return Sparkles;
  if (
    event.eventType.startsWith("committee") ||
    event.eventType.startsWith("assessment")
  )
    return Bot;
  if (event.eventType.startsWith("expression")) return Waypoints;
  if (event.eventType.startsWith("audit")) return ShieldCheck;
  if (event.eventType.startsWith("position")) return CheckCircle2;
  return CircleDot;
}

function entityFor(
  event: AltaEvent,
  status: MvpStatus,
  domain: (value: string) => string,
): SelectedEntity {
  const opportunity = status.opportunities.find(
    (item) => item.id === event.aggregateId,
  );
  if (event.aggregateType === "opportunity")
    return {
      kind: "opportunity",
      id: event.aggregateId,
      label: opportunity?.title ?? event.aggregateId,
      summary: event.payload,
    };
  if (event.aggregateType === "run")
    return {
      kind: "run",
      id: event.aggregateId,
      label: event.aggregateId,
      summary: event.payload,
    };
  if (event.aggregateType === "expression")
    return {
      kind: "expression",
      id: event.aggregateId,
      label: event.aggregateId,
      summary: event.payload,
    };
  return {
    kind: "event",
    id: event.eventId,
    label: domain(event.eventType),
    summary: event as unknown as Record<string, unknown>,
  };
}

export function DecisionLedger({
  events,
  status,
  selected,
  onSelect,
  onLoadOlder,
  loadingOlder,
  hasOlder,
}: {
  events: AltaEvent[];
  status: MvpStatus;
  selected: SelectedEntity | null;
  onSelect: (entity: SelectedEntity) => void;
  onLoadOlder: () => Promise<void>;
  loadingOlder: boolean;
  hasOlder: boolean;
}) {
  const { clock, domain, relative, t } = useI18n();
  const [query, setQuery] = useState("");
  const [family, setFamily] = useState("all");
  const [scope, setScope] = useState("all");
  const currentOpportunity = status.opportunities[0]?.id;
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return events.filter((event) => {
      const haystack =
        `${event.eventType} ${event.aggregateType} ${event.aggregateId} ${JSON.stringify(event.payload)}`.toLowerCase();
      const eventFamily = event.eventType.split(/[._]/)[0];
      const inScope =
        scope === "all" ||
        (scope === "cycle" &&
          Boolean(status.currentPipelineId) &&
          haystack.includes(String(status.currentPipelineId).toLowerCase())) ||
        (scope === "opportunity" &&
          Boolean(currentOpportunity) &&
          haystack.includes(String(currentOpportunity).toLowerCase()));
      return (
        (!needle || haystack.includes(needle)) &&
        (family === "all" || eventFamily === family) &&
        inScope
      );
    });
  }, [
    currentOpportunity,
    events,
    family,
    query,
    scope,
    status.currentPipelineId,
  ]);
  const families = useMemo(
    () =>
      [
        ...new Set(events.map((event) => event.eventType.split(/[._]/)[0])),
      ].sort(),
    [events],
  );
  return (
    <section className="ledger-shell" aria-labelledby="ledger-title">
      <div className="ledger-heading">
        <h2 id="ledger-title">{t("chronologicalLedger")}</h2>
        <div className="ledger-meta">
          <CalendarClock />
          <span>{t("loadedEvents", { count: events.length })}</span>
          <StatusPill status="append only" />
        </div>
      </div>
      <div className="ledger-tools">
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t("ledgerFilterPlaceholder")}
          aria-label={t("filterLoadedEvents")}
        />
        <select
          value={family}
          onChange={(event) => setFamily(event.target.value)}
          aria-label={t("filterEventFamily")}
        >
          <option value="all">{t("allEventFamilies")}</option>
          {families.map((value) => (
            <option value={value} key={value}>
              {domain(value)}
            </option>
          ))}
        </select>
        <select
          value={scope}
          onChange={(event) => setScope(event.target.value)}
          aria-label={t("filterDecisionScope")}
        >
          <option value="all">{t("allLoadedScopes")}</option>
          {status.currentPipelineId && (
            <option value="cycle">{t("currentCycle")}</option>
          )}
          {currentOpportunity && (
            <option value="opportunity">{t("leadingOpportunity")}</option>
          )}
        </select>
        <Button
          variant="outline"
          disabled={!hasOlder || loadingOlder}
          onClick={() => void onLoadOlder()}
        >
          {loadingOlder
            ? t("loading")
            : hasOlder
              ? t("loadOlder")
              : t("historyStartReached")}
        </Button>
      </div>
      <ScrollArea className="ledger-scroll">
        <div className="ledger-list">
          {filtered.map((event) => {
            const Icon = iconFor(event);
            const target = entityFor(event, status, domain);
            return (
              <button
                className={cn(
                  "ledger-row",
                  selected?.id === target.id && "is-selected",
                )}
                key={event.eventId}
                onClick={() => onSelect(target)}
              >
                <time dateTime={event.knownAt}>
                  <strong>{clock(event.knownAt)}</strong>
                  <span>{relative(event.knownAt)}</span>
                </time>
                <span className="ledger-rail">
                  <span className="ledger-icon">
                    <Icon />
                  </span>
                </span>
                <span className="ledger-copy">
                  <strong>{domain(event.eventType)}</strong>
                  <small>
                    {domain(event.aggregateType)} · {event.aggregateId}
                  </small>
                </span>
                <span className="ledger-payload">
                  {summarize(
                    event.payload,
                    domain,
                    t("recordedWithoutSummary"),
                  )}
                </span>
                <span className="ledger-cursor">#{event.cursor}</span>
              </button>
            );
          })}
          {!filtered.length && (
            <div className="ledger-empty">
              <CalendarClock />
              <h3>
                {events.length ? t("noMatchingEvents") : t("noRecordedEvents")}
              </h3>
              <p>{events.length ? t("broadenFilters") : t("ledgerWillFill")}</p>
            </div>
          )}
        </div>
      </ScrollArea>
    </section>
  );
}

function summarize(
  payload: Record<string, unknown>,
  domain: (value: string) => string,
  emptyLabel: string,
) {
  const candidate =
    payload.summary ??
    payload.status ??
    payload.verdict ??
    payload.stage ??
    payload.role;
  if (typeof candidate === "string") return domain(candidate);
  const keys = Object.keys(payload).slice(0, 3);
  return keys.length ? keys.map(domain).join(" · ") : emptyLabel;
}
