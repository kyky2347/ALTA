import type { MvpStatus } from "@/lib/types";

export type SourceRecord = MvpStatus["sources"][number];

export type SourceSummary = {
  identity: string;
  latest: SourceRecord;
  history: SourceRecord[];
};

const ISSUE_POSTURES = new Set([
  "degraded",
  "failed",
  "rate_limited",
  "stale",
  "unavailable",
]);

function text(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function sourceTimestamp(source: SourceRecord) {
  const parsed = Date.parse(source.knownAt);
  return Number.isFinite(parsed) ? parsed : null;
}

export function sourceIdentity(source: SourceRecord) {
  const explicit =
    text(source.sourceId) ??
    text(source.source_id) ??
    text(source.providerId) ??
    text(source.provider);
  if (explicit) return explicit;
  const id = source.id.trim();
  const separator = id.lastIndexOf(":");
  return separator >= 0 && separator < id.length - 1
    ? id.slice(separator + 1)
    : id;
}

export function readableSourceIssue(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  const summary =
    record.message ?? record.reason ?? record.code ?? record.status;
  return typeof summary === "string" ? summary : null;
}

export function recordedSourceIssue(source: SourceRecord) {
  const posture = String(source.posture ?? source.status ?? "recorded");
  const directIssue =
    source.error ?? source.lastError ?? source.errorCode ?? source.failure;
  const issueValue =
    directIssue ??
    (ISSUE_POSTURES.has(posture.toLowerCase()) ? source.reason : null);
  return readableSourceIssue(issueValue);
}

/**
 * Fold per-cycle posture events into the latest durable state per source.
 * Issues remain first, the rendered identity count is bounded, and every
 * omitted record is represented by an explicit count in the returned model.
 */
export function summarizeSourceRecords(sources: SourceRecord[], limit = 12) {
  const grouped = new Map<
    string,
    Array<{ source: SourceRecord; inputIndex: number }>
  >();
  sources.forEach((source, inputIndex) => {
    const identity = sourceIdentity(source);
    const records = grouped.get(identity) ?? [];
    records.push({ source, inputIndex });
    grouped.set(identity, records);
  });

  const summaries = [...grouped.entries()].map(([identity, records]) => {
    records.sort((left, right) => {
      const leftTime = sourceTimestamp(left.source);
      const rightTime = sourceTimestamp(right.source);
      if (leftTime !== null && rightTime !== null && leftTime !== rightTime)
        return rightTime - leftTime;
      if (leftTime !== null && rightTime === null) return -1;
      if (leftTime === null && rightTime !== null) return 1;
      return left.inputIndex - right.inputIndex;
    });
    return {
      identity,
      latest: records[0].source,
      history: records.slice(1).map(({ source }) => source),
    } satisfies SourceSummary;
  });

  summaries.sort((left, right) => {
    const issueDifference =
      Number(recordedSourceIssue(right.latest) !== null) -
      Number(recordedSourceIssue(left.latest) !== null);
    if (issueDifference) return issueDifference;
    const leftTime = sourceTimestamp(left.latest) ?? Number.NEGATIVE_INFINITY;
    const rightTime = sourceTimestamp(right.latest) ?? Number.NEGATIVE_INFINITY;
    return rightTime - leftTime || left.identity.localeCompare(right.identity);
  });

  const boundedLimit = Math.max(1, Math.floor(limit));
  return {
    visible: summaries.slice(0, boundedLimit),
    hiddenIdentityCount: Math.max(0, summaries.length - boundedLimit),
    foldedRecordCount: Math.max(0, sources.length - summaries.length),
    totalIdentityCount: summaries.length,
  };
}
