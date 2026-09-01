export function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function recordList(value: unknown) {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const record = asRecord(item);
        return record ? [record] : [];
      })
    : [];
}

export function hasReadableValue(value: unknown): boolean {
  if (value === null || value === undefined || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  const record = asRecord(value);
  return record ? Object.keys(record).length > 0 : true;
}

export function readableValue(
  input: unknown,
  formatter: {
    domain: (value: string) => string;
    fallback: string;
    localize: boolean;
    value: (value: unknown) => string;
  },
  depth = 0,
): string {
  if (!hasReadableValue(input)) return formatter.fallback;
  if (Array.isArray(input))
    return input
      .slice(0, 20)
      .map((item) => readableValue(item, formatter, depth + 1))
      .join(" · ");
  const record = asRecord(input);
  if (record) {
    if (depth >= 2) return recordSummary(record, formatter.fallback);
    return Object.entries(record)
      .slice(0, 20)
      .map(
        ([key, item]) =>
          `${formatter.domain(key)}: ${readableValue(item, formatter, depth + 1)}`,
      )
      .join("\n");
  }
  if (typeof input === "string" && formatter.localize)
    return formatter.domain(input);
  return formatter.value(input);
}

function recordSummary(value: Record<string, unknown>, fallback: string) {
  const summary =
    value.summary ??
    value.rationale ??
    value.thesis ??
    value.text ??
    value.code;
  return typeof summary === "string" ? summary : fallback;
}
