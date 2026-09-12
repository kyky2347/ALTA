import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { AgentMark } from "@/components/agent-mark";
import { StatusPill } from "@/components/status-pill";
import { useI18n } from "@/lib/i18n";
import { researchLibrary, researchScouts } from "@/lib/research-library";
import type { MvpStatus, RuntimeDetail, SelectedEntity } from "@/lib/types";
import { readableMindSummary } from "@/lib/utils";
import "./research-library.css";

export function ResearchLibrary({
  status,
  minds,
  onSelect,
}: {
  status: MvpStatus;
  minds: RuntimeDetail["minds"];
  onSelect: (record: SelectedEntity) => void;
}) {
  const { t, domain, relative, number } = useI18n();
  const [scope, setScope] = useState<"week" | "snapshot">("week");
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(8);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 60000);
    return () => window.clearInterval(id);
  }, []);
  const rows = useMemo(
    () => researchLibrary(status, now, scope, query),
    [status, now, scope, query],
  );
  const visible = rows.slice(0, limit);
  const scouts = researchScouts(status.agents, now);
  return (
    <section
      className="research-library"
      aria-labelledby="research-library-title"
    >
      <div className="research-library-heading">
        <div>
          <h2 id="research-library-title">{t("researchLibraryTitle")}</h2>
          <p>{t("researchLibraryHelp")}</p>
        </div>
        <span className="research-library-count" role="status">
          {t("researchLibraryCount", {
            visible: number(visible.length),
            total: number(rows.length),
          })}
        </span>
      </div>
      {scouts.length > 0 && (
        <div
          className="research-scouts"
          aria-label={t("researchLibraryScouts")}
        >
          <p className="research-scouts-label">{t("researchLibraryScouts")}</p>
          <div className="research-scout-grid">
            {scouts.map((agent) => (
              <button
                type="button"
                className="research-scout-card"
                key={agent.runId}
                onClick={() =>
                  onSelect({
                    kind: "run",
                    id: agent.runId,
                    label: domain(agent.id),
                    summary: agent as unknown as Record<string, unknown>,
                  })
                }
              >
                <div>
                  <AgentMark role={agent.id} />
                  <StatusPill
                    status={agent.status}
                    live={agent.status === "running"}
                  />
                </div>
                <strong>{domain(agent.id)}</strong>
                <p className="research-scout-finding">
                  <small>{t("researchLibraryFinding")}</small>
                  {readableMindSummary(
                    minds.find((mind) => mind.id === agent.id)?.rollingSummary,
                  ) ?? t("noRollingSummarySaved")}
                </p>
                <span>{agent.modelId ?? agent.modelProvider ?? "—"}</span>
                <time dateTime={agent.knownAt}>{relative(agent.knownAt)}</time>
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="research-library-toolbar">
        <div className="research-library-search">
          <Search aria-hidden="true" />
          <Input
            type="search"
            maxLength={160}
            value={query}
            aria-label={t("researchLibrarySearch")}
            placeholder={t("researchLibrarySearch")}
            onChange={(e) => {
              setQuery(e.target.value);
              setLimit(8);
            }}
          />
        </div>
        <div
          className="research-library-scopes"
          role="group"
          aria-label={t("researchLibraryScope")}
        >
          {(["week", "snapshot"] as const).map((s) => (
            <Button
              key={s}
              variant={s === scope ? "secondary" : "ghost"}
              aria-pressed={s === scope}
              onClick={() => {
                setScope(s);
                setLimit(8);
              }}
            >
              {t(
                s === "week"
                  ? "researchLibraryWeek"
                  : "researchLibrarySnapshot",
              )}
            </Button>
          ))}
        </div>
      </div>
      <div className="research-library-grid">
        {visible.map((row) => (
          <button
            type="button"
            className="research-record-card"
            key={`${row.kind}:${row.id}`}
            onClick={() =>
              onSelect({
                kind: row.kind,
                id: row.id,
                label: row.title,
                summary: row.summary,
              })
            }
          >
            <div className="research-record-top">
              <Badge variant="outline">
                {t(
                  row.kind === "candidate"
                    ? "researchLibraryCandidate"
                    : "researchOpportunity",
                )}
              </Badge>
              <span>{domain(row.freshnessState)}</span>
            </div>
            <h3>{row.title}</h3>
            <p>
              {t(
                row.kind === "candidate"
                  ? "researchLibraryLeadOnly"
                  : row.current
                    ? "researchLibraryUnderReview"
                    : "researchLibraryHistorical",
              )}
            </p>
            <div className="research-record-bottom">
              <time dateTime={row.knownAt} title={row.knownAt}>
                {relative(row.knownAt)}
              </time>
              <span>
                {t("researchLibraryInspect")}{" "}
                <ArrowUpRight aria-hidden="true" />
              </span>
            </div>
          </button>
        ))}
      </div>
      {!rows.length && (
        <p className="research-library-empty">{t("researchLibraryEmpty")}</p>
      )}
      {rows.length > limit && (
        <Button variant="outline" onClick={() => setLimit((v) => v + 8)}>
          {t("researchLibraryMore")}
        </Button>
      )}
    </section>
  );
}
