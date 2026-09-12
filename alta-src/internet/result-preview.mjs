// Keep source identity attached to bounded tool records. Cutting serialized JSON
// at a byte offset can discard trailing provenance and break evidence binding.
const IDENTITY_KEYS = new Set([
  "url",
  "source_url",
  "source_locator",
  "canonical_url",
  "provenance",
  "metadata",
  "source",
  "dataset",
  "symbol",
  "title",
  "date",
  "period",
  "published_at",
  "published_time",
  "observed_at",
  "timestamp",
  "error",
  "cached",
  "stale",
  "truncated",
  "partial",
  "no_results",
  "text_start",
  "text_end",
  "total_chars",
  "focus_matched",
  "interpretation",
  "freshness",
]);
const URL_KEYS = new Set([
  "url",
  "source_url",
  "source_locator",
  "canonical_url",
]);

function project(value, scale, depth = 0, key = "") {
  if (typeof value === "string") {
    // Never turn a partial URL into an apparently valid citation.
    if (URL_KEYS.has(key)) return value.length <= 2_048 ? value : null;
    const limit = Math.max(64, Math.floor(4_000 * scale));
    return value.length <= limit
      ? value
      : key === "text"
        ? value.slice(0, limit)
        : `${value.slice(0, limit)}…`;
  }
  if (value === null || typeof value !== "object") return value;
  if (depth >= 10) return null;
  if (Array.isArray(value))
    return value
      .slice(0, Math.max(1, Math.floor(20 * Math.sqrt(scale))))
      .map((item) => project(item, scale, depth + 1));
  const entries = Object.entries(value).sort(
    ([a], [b]) => Number(IDENTITY_KEYS.has(b)) - Number(IDENTITY_KEYS.has(a)),
  );
  const projected = Object.fromEntries(
    entries
      .slice(
        0,
        Math.max(
          entries.filter(([name]) => IDENTITY_KEYS.has(name)).length,
          8,
          Math.floor(128 * scale),
        ),
      )
      .map(([name, item]) => [name, project(item, scale, depth + 1, name)]),
  );
  if (typeof value.text === "string" && projected.text !== value.text) {
    projected.truncated = true;
    if (
      typeof projected.text === "string" &&
      Number.isInteger(projected.text_start)
    )
      projected.text_end = projected.text_start + projected.text.length;
  }
  return projected;
}

export function boundedToolPreview(value, maximumBytes) {
  const original = JSON.stringify(value, null, 2);
  const originalBytes = Buffer.byteLength(original);
  if (originalBytes <= maximumBytes)
    return { value, text: original, truncated: false };
  for (let scale = 1; scale >= 1 / 256; scale /= 2) {
    const preview = {
      ...project(value, scale),
      truncated: true,
      original_bytes: originalBytes,
    };
    const text = JSON.stringify(preview);
    if (Buffer.byteLength(text) <= maximumBytes)
      return { value: preview, text, truncated: true };
  }
  const preview = { truncated: true, original_bytes: originalBytes };
  return { value: preview, text: JSON.stringify(preview), truncated: true };
}
