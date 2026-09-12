function date(value) {
  if (value == null || value === "") return "";
  const text = String(value);
  const parsed = new Date(`${text}T00:00:00Z`);
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(text) ||
    Number.isNaN(parsed.valueOf()) ||
    parsed.toISOString().slice(0, 10) !== text
  )
    throw Object.assign(new Error("Feed dates must use valid YYYY-MM-DD"), {
      status: 400,
      code: "alta_feed_invalid_date",
    });
  return text;
}

export function feedFilter(args) {
  if (
    args.query != null &&
    (typeof args.query !== "string" || args.query.length > 200)
  )
    throw Object.assign(
      new Error("Feed query must be at most 200 characters"),
      { status: 400, code: "alta_feed_invalid_query" },
    );
  const from = date(args.from_date);
  const to = date(args.to_date);
  if (from && to && from > to)
    throw Object.assign(new Error("Feed from_date must not exceed to_date"), {
      status: 400,
      code: "alta_feed_invalid_date",
    });
  const terms =
    (args.query ?? "").toLocaleLowerCase("en").match(/[\p{L}\p{N}]+/gu) ?? [];
  return { from, to, terms };
}

export function filterFeedItems(items, filter) {
  return items.filter((item) => {
    const text = `${item.title} ${item.summary}`.toLocaleLowerCase("en");
    if (!filter.terms.every((term) => text.includes(term))) return false;
    if (!filter.from && !filter.to) return true;
    const timestamp = Date.parse(item.published);
    if (!Number.isFinite(timestamp)) return false;
    const day = new Date(timestamp).toISOString().slice(0, 10);
    return (
      (!filter.from || day >= filter.from) && (!filter.to || day <= filter.to)
    );
  });
}

export function assertFeedDocument(text) {
  try {
    const value = JSON.parse(text);
    if (Array.isArray(value.items)) return;
  } catch {}
  if (/<(?:rss|feed|rdf:RDF)\b/i.test(text) && !/<html\b/i.test(text)) return;
  throw Object.assign(
    new Error("Source did not return an RSS, Atom or JSON feed"),
    { status: 502, code: "alta_feed_invalid_document" },
  );
}
