import { useEffect, useState } from "react";
import {
  Bot,
  Braces,
  Clock3,
  FileKey2,
  FileText,
  Fingerprint,
  ShieldCheck,
  Sparkles,
  Waypoints,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { entityDetailPath, getJson } from "@/lib/api";
import { clockTime, relativeTime, titleCase, valueText } from "@/lib/display";
import type { MvpStatus, SelectedEntity } from "@/lib/types";

export function DetailInspector({
  selected,
  status,
  preview,
}: {
  selected: SelectedEntity | null;
  status: MvpStatus | null;
  preview: boolean;
}) {
  const [request, setRequest] = useState<{
    path: string;
    detail: Record<string, unknown> | null;
    error: string | null;
  } | null>(null);
  const path = selected ? entityDetailPath(selected.kind, selected.id) : null;

  useEffect(() => {
    if (preview || !path) return;
    let active = true;
    getJson<Record<string, unknown>>(path)
      .then((detail) => active && setRequest({ path, detail, error: null }))
      .catch(
        (reason) =>
          active && setRequest({ path, detail: null, error: reason.message }),
      );
    return () => {
      active = false;
    };
  }, [path, preview]);

  const detail =
    preview || !path
      ? (selected?.summary ?? null)
      : request?.path === path
        ? request.detail
        : null;
  const loading = Boolean(path && !preview && request?.path !== path);
  const error = request?.path === path ? request.error : null;

  const opportunityAssessments =
    selected?.kind === "opportunity"
      ? (status?.assessments.filter(
          (item) => item.opportunityId === selected.id,
        ) ?? [])
      : [];
  const discussions =
    selected?.kind === "opportunity"
      ? (status?.discussions.filter(
          (item) => item.opportunityId === selected.id,
        ) ?? [])
      : [];
  const Icon =
    selected?.kind === "opportunity"
      ? Sparkles
      : selected?.kind === "run"
        ? Bot
        : selected?.kind === "expression"
          ? Waypoints
          : selected?.kind === "position"
            ? ShieldCheck
            : Braces;

  return (
    <aside className="inspector" aria-label="Selected record inspector">
      <div className="inspector-head">
        <div
          className="inspector-kicker"
          aria-label={
            selected ? `${titleCase(selected.kind)} record` : "Inspector"
          }
        >
          <span className="inspector-icon">
            <Icon />
          </span>
        </div>
        {selected ? (
          <Badge variant="outline" className="inspector-id">
            {selected.id}
          </Badge>
        ) : null}
      </div>
      {!selected ? (
        <div className="inspector-empty">
          <Fingerprint />
          <h2>Select any record</h2>
          <p>
            Open an opportunity, agent run, committee event, expression, or
            shadow position to inspect its durable record.
          </p>
        </div>
      ) : (
        <>
          <div className="inspector-title">
            <h2>{selected.label}</h2>
            <p>Saved system record · not private chain-of-thought</p>
          </div>
          <Tabs defaultValue="brief" className="inspector-tabs">
            <TabsList>
              <TabsTrigger value="brief">Brief</TabsTrigger>
              <TabsTrigger value="evidence">Evidence</TabsTrigger>
              <TabsTrigger value="record">Record</TabsTrigger>
            </TabsList>
            <ScrollArea className="inspector-scroll">
              <TabsContent value="brief">
                {loading ? (
                  <InspectorLoading />
                ) : error ? (
                  <InspectorError error={error} />
                ) : (
                  <Brief
                    detail={detail}
                    selected={selected}
                    assessments={opportunityAssessments}
                    discussions={discussions}
                  />
                )}
              </TabsContent>
              <TabsContent value="evidence">
                <Evidence
                  detail={detail}
                  assessments={opportunityAssessments}
                  discussions={discussions}
                />
              </TabsContent>
              <TabsContent value="record">
                <div className="raw-label">
                  <Braces /> Normalized JSON
                </div>
                <pre className="raw-record">
                  {JSON.stringify(detail ?? selected.summary ?? {}, null, 2)}
                </pre>
              </TabsContent>
            </ScrollArea>
          </Tabs>
        </>
      )}
      <div className="inspector-foot">
        <ShieldCheck />
        <span>Research-only · shadow environment · capital disabled</span>
      </div>
    </aside>
  );
}

function Brief({
  detail,
  selected,
  assessments,
  discussions,
}: {
  detail: Record<string, unknown> | null;
  selected: SelectedEntity;
  assessments: Array<Record<string, unknown>>;
  discussions: Array<Record<string, unknown>>;
}) {
  const leadFields = [
    "status",
    "thesis",
    "whyNow",
    "mechanism",
    "direction",
    "horizonDays",
    "falsifier",
    "recommendation",
    "rationale",
    "kind",
    "symbol",
    "side",
    "knownAt",
    "modelProvider",
    "modelId",
    "latencyMs",
    "attemptCount",
  ];
  const fields = leadFields.filter((key) => detail?.[key] !== undefined);
  return (
    <div className="inspector-sections">
      <section className="inspector-section">
        <h3>
          <FileText /> Decision packet
        </h3>
        <div className="fact-list">
          {fields.length ? (
            fields.map((key) => (
              <div className="fact-row" key={key}>
                <span>{titleCase(key)}</span>
                <strong>{valueText(detail?.[key])}</strong>
              </div>
            ))
          ) : (
            <p className="muted-copy">
              {valueText(selected.summary) ||
                "No public brief has been saved for this record."}
            </p>
          )}
        </div>
      </section>
      {assessments.length > 0 && (
        <section className="inspector-section">
          <h3>
            <Bot /> Independent assessments
          </h3>
          <div className="assessment-stack">
            {assessments.map((assessment) => (
              <article className="assessment-card" key={String(assessment.id)}>
                <div>
                  <strong>{titleCase(String(assessment.assessor))}</strong>
                  <Badge variant="outline">{String(assessment.verdict)}</Badge>
                </div>
                <p>
                  {String(
                    assessment.recommendation ?? "No recommendation summary",
                  )}
                </p>
                <small>
                  Score {String(assessment.score)} · confidence{" "}
                  {String(assessment.confidence ?? "—")}
                </small>
              </article>
            ))}
          </div>
        </section>
      )}
      {discussions.length > 0 && (
        <section className="inspector-section">
          <h3>
            <Clock3 /> Committee exchange
          </h3>
          {discussions.map((item) => (
            <article className="discussion-item" key={String(item.id)}>
              <span>{titleCase(String(item.eventType))}</span>
              <p>{summaryFrom(item.detail)}</p>
              <small>
                {clockTime(String(item.knownAt))} ·{" "}
                {relativeTime(String(item.knownAt))}
              </small>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}

function Evidence({
  detail,
  assessments,
  discussions,
}: {
  detail: Record<string, unknown> | null;
  assessments: Array<Record<string, unknown>>;
  discussions: Array<Record<string, unknown>>;
}) {
  const artifacts = Array.isArray(detail?.artifacts)
    ? (detail.artifacts as Array<Record<string, unknown>>)
    : [];
  const evidenceIds = Array.isArray(detail?.evidenceIds)
    ? detail.evidenceIds
    : [];
  return (
    <div className="inspector-sections">
      <section className="inspector-section">
        <h3>
          <FileKey2 /> Provenance
        </h3>
        <div className="fact-list">
          <div className="fact-row">
            <span>Evidence references</span>
            <strong>{evidenceIds.length || "None saved"}</strong>
          </div>
          <div className="fact-row">
            <span>Artifacts</span>
            <strong>{artifacts.length}</strong>
          </div>
          <div className="fact-row">
            <span>Committee records</span>
            <strong>{assessments.length + discussions.length}</strong>
          </div>
        </div>
      </section>
      {artifacts.map((artifact, index) => (
        <section
          className="artifact-card"
          key={`${String(artifact.kind)}-${index}`}
        >
          <div>
            <FileText />
            <strong>
              {titleCase(String(artifact.kind ?? `Artifact ${index + 1}`))}
            </strong>
          </div>
          <p>{summaryFrom(artifact.content)}</p>
          <small>
            {artifact.contentHash
              ? `Hash ${String(artifact.contentHash).slice(0, 14)}…`
              : "Hash unavailable"}
          </small>
        </section>
      ))}
      {!artifacts.length && (
        <div className="inspector-note">
          No run artifact is attached to this selected record. Opportunity
          evidence may be represented through assessments and committee events.
        </div>
      )}
    </div>
  );
}

function summaryFrom(value: unknown) {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return "No public summary";
  const object = value as Record<string, unknown>;
  const summary =
    object.summary ?? object.rationale ?? object.thesis ?? object.text;
  return typeof summary === "string"
    ? summary
    : JSON.stringify(object).slice(0, 240);
}

function InspectorLoading() {
  return (
    <div className="inspector-state">
      <span className="loading-orbit" />
      <p>Loading the durable record…</p>
    </div>
  );
}
function InspectorError({ error }: { error: string }) {
  return (
    <div className="inspector-state is-error">
      <ShieldCheck />
      <p>{error}</p>
    </div>
  );
}
