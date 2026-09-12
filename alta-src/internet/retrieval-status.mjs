// Preserve retrieval diagnostics through compact projections. None of these
// fields supplies a publication time or establishes that a thesis is current.
const STATUS_FIELDS = [
  "cached",
  "stale",
  "truncated",
  "no_results",
  "partial",
  "text_start",
  "text_end",
  "total_chars",
  "focus_matched",
];

export function retrievalStatus(value) {
  return Object.fromEntries(
    STATUS_FIELDS.filter((key) => value[key] !== undefined).map((key) => [
      key,
      value[key],
    ]),
  );
}
