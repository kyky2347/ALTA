import { useEffect, useRef, useState } from "react";
import {
  Bot,
  Braces,
  Clock3,
  FileKey2,
  FileText,
  Fingerprint,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  Waypoints,
  X,
} from "lucide-react";
import { OpportunityDossier } from "@/components/opportunity-dossier";
import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { entityDetailPath, getJson } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { recordList } from "@/lib/readable-record";
import type { MvpStatus, SelectedEntity } from "@/lib/types";

const DOMAIN_VALUE_FIELDS = new Set(["status", "direction", "kind", "side"]);
const DETAIL_CACHE_TTL_MS = 15_000;
const DETAIL_CACHE_MAX_ENTRIES = 64;
const detailCache = new Map<
  string,
  { loadedAt: number; detail: Record<string, unknown> }
>();

type DetailRequest = {
  path: string;
  status: "loaded" | "error";
  detail: Record<string, unknown> | null;
  error: string | null;
  loadedAt: number | null;
};

function cacheDetail(path: string, detail: Record<string, unknown>) {
  detailCache.delete(path);
  detailCache.set(path, { loadedAt: Date.now(), detail });
  while (detailCache.size > DETAIL_CACHE_MAX_ENTRIES) {
    const oldest = detailCache.keys().next().value;
    if (oldest === undefined) break;
    detailCache.delete(oldest);
  }
}

export function DetailInspector({
  selected,
  status,
  preview,
  selectionExpired,
  liveFallbackAvailable,
  onClose,
}: {
  selected: SelectedEntity | null;
  status: MvpStatus | null;
  preview: boolean;
  selectionExpired: boolean;
  liveFallbackAvailable: boolean;
  onClose: () => void;
}) {
  const { domain, systemMessage, t } = useI18n();
  const [request, setRequest] = useState<DetailRequest | null>(null);
  const [forcedRefresh, setForcedRefresh] = useState<{
    path: string;
    nonce: number;
  } | null>(null);
  const [pageVisible, setPageVisible] = useState(
    () => document.visibilityState !== "hidden",
  );
  const retryAttempts = useRef(new Map<string, number>());
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    panel.current?.focus({ preventScroll: true });
    if (window.matchMedia("(max-width: 1220px)").matches) {
      panel.current?.scrollIntoView({ block: "start", behavior: "instant" });
    }
  }, [selected?.id]);
  const path = selected ? entityDetailPath(selected.kind, selected.id) : null;
  const cachedEntry = path ? (detailCache.get(path) ?? null) : null;

  useEffect(() => {
    const updateVisibility = () =>
      setPageVisible(document.visibilityState !== "hidden");
    document.addEventListener("visibilitychange", updateVisibility);
    return () =>
      document.removeEventListener("visibilitychange", updateVisibility);
  }, []);

  useEffect(() => {
    if (preview || !path || !pageVisible) return;
    const cached = detailCache.get(path);
    const force = forcedRefresh?.path === path;
    if (
      cached &&
      Date.now() - cached.loadedAt < DETAIL_CACHE_TTL_MS &&
      !force
    ) {
      const refreshIn = Math.max(
        250,
        DETAIL_CACHE_TTL_MS - (Date.now() - cached.loadedAt),
      );
      const timer = window.setTimeout(
        () =>
          setForcedRefresh((current) => ({
            path,
            nonce: current?.path === path ? current.nonce + 1 : 1,
          })),
        refreshIn,
      );
      return () => window.clearTimeout(timer);
    }
    let active = true;
    let retryTimer: number | null = null;
    const controller = new AbortController();
    getJson<Record<string, unknown>>(path, { signal: controller.signal })
      .then((detail) => {
        if (!active) return;
        retryAttempts.current.delete(path);
        cacheDetail(path, detail);
        const loadedAt = detailCache.get(path)?.loadedAt ?? Date.now();
        setRequest({
          path,
          status: "loaded",
          detail,
          error: null,
          loadedAt,
        });
        setForcedRefresh((current) =>
          current?.path === path ? null : current,
        );
      })
      .catch((reason) => {
        if (!active) return;
        const message =
          reason instanceof Error
            ? reason.message
            : "The durable record could not be loaded.";
        setRequest((current) => ({
          path,
          status: "error",
          detail:
            cached?.detail ?? (current?.path === path ? current.detail : null),
          error: message,
          loadedAt:
            cached?.loadedAt ??
            (current?.path === path ? current.loadedAt : null),
        }));
        const attempt = (retryAttempts.current.get(path) ?? 0) + 1;
        retryAttempts.current.set(path, attempt);
        const retryIn = Math.min(60_000, 2_000 * 2 ** Math.min(attempt - 1, 5));
        retryTimer = window.setTimeout(
          () =>
            setForcedRefresh((current) => ({
              path,
              nonce: current?.path === path ? current.nonce + 1 : 1,
            })),
          retryIn,
        );
      });
    return () => {
      active = false;
      controller.abort();
      if (retryTimer !== null) window.clearTimeout(retryTimer);
    };
  }, [forcedRefresh, pageVisible, path, preview]);

  const activeRequest = request?.path === path ? request : null;
  const detail =
    preview || !path
      ? (selected?.summary ?? null)
      : (activeRequest?.detail ?? cachedEntry?.detail ?? null);
  const error = activeRequest?.status === "error" ? activeRequest.error : null;
  const loading = Boolean(
    path &&
      !preview &&
      !error &&
      (forcedRefresh?.path === path || !cachedEntry),
  );
  const loadedAt = activeRequest?.loadedAt ?? cachedEntry?.loadedAt ?? null;
  const stale = Boolean(detail && (error || (loading && loadedAt)));

  const retryDetail = () => {
    if (!path) return;
    retryAttempts.current.delete(path);
    setRequest((current) =>
      current?.path === path
        ? { ...current, status: "loaded", error: null }
        : current,
    );
    setForcedRefresh((current) => ({
      path,
      nonce: current?.path === path ? current.nonce + 1 : 1,
    }));
  };

  const savedAssessments = recordList(detail?.assessments);
  const savedDiscussions = recordList(detail?.discussions);
  const opportunityAssessments = savedAssessments.length
    ? savedAssessments
    : selected?.kind === "opportunity"
      ? (status?.assessments
          .filter((item) => item.opportunityId === selected.id)
          .map((item) => item as unknown as Record<string, unknown>) ?? [])
      : [];
  const discussions = savedDiscussions.length
    ? savedDiscussions
    : selected?.kind === "opportunity"
      ? (status?.discussions
          .filter((item) => item.opportunityId === selected.id)
          .map((item) => item as unknown as Record<string, unknown>) ?? [])
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
    <aside
      ref={panel}
      className="inspector"
      tabIndex={-1}
      aria-label={t("selectedRecordInspector")}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          onClose();
        }
      }}
    >
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
          <Badge variant="outline" className="inspector-id" title={selected.id}>
            {selected.id}
          </Badge>
        ) : null}
        <Button
          variant="ghost"
          size="icon"
          className="inspector-close"
          aria-label={t("closeDetails")}
          title={t("closeDetails")}
          onClick={onClose}
        >
          <X />
        </Button>
      </div>
      {selectionExpired && (
        <SelectionExpiredNotice hasFallback={liveFallbackAvailable} />
      )}
      {selected?.kind === "position" && !preview && (
        <BoundedPositionNotice snapshotOnly={selected.snapshotOnly === true} />
      )}
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
            <DetailFreshnessNotice
              error={error ? (systemMessage(error) ?? error) : null}
              loading={loading}
              loadedAt={loadedAt}
              stale={stale}
              onRetry={retryDetail}
            />
            <ScrollArea className="inspector-scroll">
              <TabsContent value="brief">
                {loading && !detail ? (
                  <InspectorLoading />
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

function BoundedPositionNotice({ snapshotOnly }: { snapshotOnly: boolean }) {
  const { t } = useI18n();
  return (
    <Alert className="inspector-data-notice" role="status">
      <ShieldCheck />
      <AlertTitle>
        {snapshotOnly
          ? t("positionSnapshotExpired")
          : t("boundedPositionSnapshot")}
      </AlertTitle>
      <AlertDescription>
        {snapshotOnly
          ? t("positionSnapshotExpiredDetail")
          : t("boundedPositionSnapshotDetail")}
      </AlertDescription>
    </Alert>
  );
}

function SelectionExpiredNotice({ hasFallback }: { hasFallback: boolean }) {
  const { t } = useI18n();
  return (
    <Alert className="inspector-data-notice" role="status" aria-live="polite">
      <TriangleAlert />
      <AlertTitle>{t("selectionExpired")}</AlertTitle>
      <AlertDescription>
        {hasFallback
          ? t("selectionExpiredFallbackDetail")
          : t("selectionExpiredEmptyDetail")}
      </AlertDescription>
    </Alert>
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
    "observedChange",
    "direction",
    "expectation",
    "expectationPosture",
    "variantWedge",
    "horizonDays",
    "falsifier",
    "prediction",
    "investability",
    "completeness",
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
      {selected.kind === "opportunity" && (
        <OpportunityDossier detail={detail} />
      )}
      {assessments.length > 0 && (
        <section className="inspector-section">
          <h3>
            <Bot /> {t("independentAssessments")}
          </h3>
          <div className="assessment-stack">
            {assessments.map((assessment, index) => (
              <article
                className="assessment-card"
                key={String(assessment.id ?? index)}
              >
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
          {discussions.map((item, index) => {
            const knownAt =
              typeof item.knownAt === "string" ? item.knownAt : null;
            return (
              <article
                className="discussion-item"
                key={String(item.id ?? index)}
              >
                <span>{domain(String(item.eventType ?? "committee"))}</span>
                <p>{summaryFrom(item.detail, t("noPublicSummary"))}</p>
                <small>
                  {knownAt
                    ? `${clock(knownAt)} · ${relative(knownAt)}`
                    : t("unavailable")}
                </small>
              </article>
            );
          })}
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
  return typeof summary === "string" ? summary : fallback;
}

function DetailFreshnessNotice({
  error,
  loading,
  loadedAt,
  stale,
  onRetry,
}: {
  error: string | null;
  loading: boolean;
  loadedAt: number | null;
  stale: boolean;
  onRetry: () => void;
}) {
  const { relative, t } = useI18n();
  if (!loading && !error) return null;
  const savedTime = loadedAt
    ? relative(new Date(loadedAt).toISOString())
    : t("unavailable");
  return (
    <Alert
      variant={error ? "destructive" : "default"}
      className="inspector-data-notice"
    >
      {error ? <TriangleAlert /> : <RefreshCw />}
      <AlertTitle>
        {error
          ? stale
            ? t("staleDetailRefreshFailed")
            : t("detailUnavailable")
          : stale
            ? t("refreshingSavedDetail")
            : t("loadingDurableRecord")}
      </AlertTitle>
      <AlertDescription>
        {error
          ? stale
            ? t("staleDetailRefreshFailedDetail", {
                time: savedTime,
                error,
              })
            : t("detailUnavailableDetail", { error })
          : stale
            ? t("refreshingSavedDetailDetail", { time: savedTime })
            : t("loadingDurableRecordDetail")}
      </AlertDescription>
      {error && (
        <AlertAction>
          <Button variant="outline" size="xs" onClick={onRetry}>
            <RefreshCw data-icon="inline-start" /> {t("retry")}
          </Button>
        </AlertAction>
      )}
    </Alert>
  );
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
