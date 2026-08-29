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
import { useI18n } from "@/lib/i18n";
import type { MvpStatus, SelectedEntity } from "@/lib/types";

const DOMAIN_VALUE_FIELDS = new Set(["status", "direction", "kind", "side"]);

export function DetailInspector({
  selected,
  status,
  preview,
}: {
  selected: SelectedEntity | null;
  status: MvpStatus | null;
  preview: boolean;
}) {
  const { domain, systemMessage, t } = useI18n();
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
    <aside className="inspector" aria-label={t("selectedRecordInspector")}>
      <div className="inspector-head">
        <div
          className="inspector-kicker"
          aria-label={
            selected
              ? t("recordLabel", { kind: domain(selected.kind) })
              : t("inspector")
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
          <h2>{t("selectAnyRecord")}</h2>
          <p>{t("selectAnyRecordDetail")}</p>
        </div>
      ) : (
        <>
          <div className="inspector-title">
            <h2>{selected.label}</h2>
            <p>{t("savedSystemRecord")}</p>
          </div>
          <Tabs defaultValue="brief" className="inspector-tabs">
            <TabsList>
              <TabsTrigger value="brief">{t("brief")}</TabsTrigger>
              <TabsTrigger value="evidence">{t("evidence")}</TabsTrigger>
              <TabsTrigger value="record">{t("record")}</TabsTrigger>
            </TabsList>
            <ScrollArea className="inspector-scroll">
              <TabsContent value="brief">
                {loading ? (
                  <InspectorLoading />
                ) : error ? (
                  <InspectorError error={systemMessage(error) ?? error} />
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
                  <Braces /> {t("normalizedJson")}
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
        <span>{t("researchBoundary")}</span>
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
  const { clock, domain, relative, t, value } = useI18n();
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
          <FileText /> {t("decisionPacket")}
        </h3>
        <div className="fact-list">
          {fields.length ? (
            fields.map((key) => (
              <div className="fact-row" key={key}>
                <span>{domain(key)}</span>
                <strong>
                  {DOMAIN_VALUE_FIELDS.has(key) &&
                  typeof detail?.[key] === "string"
                    ? domain(detail[key])
                    : value(detail?.[key])}
                </strong>
              </div>
            ))
          ) : (
            <p className="muted-copy">
              {value(selected.summary) || t("noPublicBrief")}
            </p>
          )}
        </div>
      </section>
      {assessments.length > 0 && (
        <section className="inspector-section">
          <h3>
            <Bot /> {t("independentAssessments")}
          </h3>
          <div className="assessment-stack">
            {assessments.map((assessment) => (
              <article className="assessment-card" key={String(assessment.id)}>
                <div>
                  <strong>{domain(String(assessment.assessor))}</strong>
                  <Badge variant="outline">
                    {domain(String(assessment.verdict))}
                  </Badge>
                </div>
                <p>
                  {String(assessment.recommendation ?? t("noRecommendation"))}
                </p>
                <small>
                  {t("scoreConfidence", {
                    score: String(assessment.score),
                    confidence: String(assessment.confidence ?? "—"),
                  })}
                </small>
              </article>
            ))}
          </div>
        </section>
      )}
      {discussions.length > 0 && (
        <section className="inspector-section">
          <h3>
            <Clock3 /> {t("committeeExchange")}
          </h3>
          {discussions.map((item) => (
            <article className="discussion-item" key={String(item.id)}>
              <span>{domain(String(item.eventType))}</span>
              <p>{summaryFrom(item.detail, t("noPublicSummary"))}</p>
              <small>
                {clock(String(item.knownAt))} · {relative(String(item.knownAt))}
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
  const { domain, t } = useI18n();
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
          <FileKey2 /> {t("provenance")}
        </h3>
        <div className="fact-list">
          <div className="fact-row">
            <span>{t("evidenceReferences")}</span>
            <strong>{evidenceIds.length || t("noneSaved")}</strong>
          </div>
          <div className="fact-row">
            <span>{t("artifacts")}</span>
            <strong>{artifacts.length}</strong>
          </div>
          <div className="fact-row">
            <span>{t("committeeRecords")}</span>
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
              {artifact.kind
                ? domain(String(artifact.kind))
                : t("artifactNumber", { number: index + 1 })}
            </strong>
          </div>
          <p>{summaryFrom(artifact.content, t("noPublicSummary"))}</p>
          <small>
            {t("originalArtifact")} ·{" "}
            {artifact.contentHash
              ? t("hash", {
                  hash: String(artifact.contentHash).slice(0, 14),
                })
              : t("hashUnavailable")}
          </small>
        </section>
      ))}
      {!artifacts.length && (
        <div className="inspector-note">{t("noArtifact")}</div>
      )}
    </div>
  );
}

function summaryFrom(value: unknown, fallback: string) {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return fallback;
  const object = value as Record<string, unknown>;
  const summary =
    object.summary ?? object.rationale ?? object.thesis ?? object.text;
  return typeof summary === "string"
    ? summary
    : JSON.stringify(object).slice(0, 240);
}

function InspectorLoading() {
  const { t } = useI18n();
  return (
    <div className="inspector-state">
      <span className="loading-orbit" />
      <p>{t("loadingDurableRecord")}</p>
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
