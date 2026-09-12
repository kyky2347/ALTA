const PERIODS = Object.freeze({ day: 1, week: 7, month: 31, year: 365 });
const BRAVE_PERIODS = Object.freeze({
  day: "pd",
  week: "pw",
  month: "pm",
  year: "py",
});
const ALIASES = Object.fromEntries(
  Object.entries(BRAVE_PERIODS).map(([a, b]) => [b, a]),
);

function validDate(value) {
  const date = new Date(`${value}T00:00:00.000Z`);
  return (
    Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value
  );
}

export function normalizeFreshness(value) {
  const input = String(value ?? "")
    .trim()
    .toLowerCase();
  const normalized = ALIASES[input] ?? input;
  if (!normalized || Object.hasOwn(PERIODS, normalized)) return normalized;
  const dates = normalized.match(/^(\d{4}-\d{2}-\d{2})to(\d{4}-\d{2}-\d{2})$/);
  if (
    dates &&
    validDate(dates[1]) &&
    validDate(dates[2]) &&
    dates[1] <= dates[2]
  )
    return normalized;
  throw Object.assign(
    new Error(
      "freshness must be day, week, month, year, pd/pw/pm/py, or YYYY-MM-DDtoYYYY-MM-DD",
    ),
    {
      status: 400,
      code: "alta_web_invalid_freshness",
    },
  );
}

export function freshnessWindow(value, now = new Date()) {
  const freshness = normalizeFreshness(value);
  if (!freshness) return null;
  const days = PERIODS[freshness];
  const [from, to] = days
    ? [
        new Date(now.getTime() - days * 86_400_000).toISOString().slice(0, 10),
        now.toISOString().slice(0, 10),
      ]
    : freshness.split("to");
  return { requested: freshness, from_date: from, to_date: to };
}

export function braveFreshness(value) {
  const freshness = normalizeFreshness(value);
  return BRAVE_PERIODS[freshness] ?? freshness;
}

export function nativeFreshness(backend, value) {
  const freshness = normalizeFreshness(value);
  return (
    backend === "brave" ||
    (backend === "searxng" && ["day", "month", "year"].includes(freshness))
  );
}

export function freshnessQuery(query, args, backend) {
  const window = args.freshness_window ?? freshnessWindow(args.freshness);
  if (!window || nativeFreshness(backend, args.freshness)) return query;
  if (backend === "xai")
    return `${query}\nResearch publication/event window: ${window.from_date} through ${window.to_date} (UTC dates). Find dated primary sources in this window; identify each actual publication/event date. Do not substitute crawl/retrieval time or an old fiscal period. Clearly separate older context and undated pages; say when no current evidence is found.`;
  // These endpoints have no verified native date-filter contract here. Query
  // terms are only a retrieval hint, never a freshness validation result.
  return `${query} after:${window.from_date} before:${new Date(Date.parse(window.to_date) + 86_400_000).toISOString().slice(0, 10)}`;
}

export function freshnessProvenance(args, backend) {
  const window = args.freshness_window ?? freshnessWindow(args.freshness);
  if (!window) return undefined;
  return {
    ...window,
    backend,
    mode: nativeFreshness(backend, args.freshness)
      ? "provider_filter"
      : "query_hint",
    event_time_verified: false,
  };
}
