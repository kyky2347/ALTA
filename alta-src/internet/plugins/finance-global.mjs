import { createHash } from "node:crypto";
import { boundedInteger } from "./support.mjs";
import {
  assertPeriodRange,
  assertRange,
  dateBefore,
  dateToday,
  invalid,
  isoDate,
  optionalText,
  period,
  provenance,
  requiredText,
} from "./finance-shared.mjs";

const RESULT_BYTES = 900;

export const GLOBAL_FINANCE_SOURCES = ["boc", "eurostat", "kraken"];
// prettier-ignore
export const GLOBAL_FINANCE_INTERVALS = { boc: 500, eurostat: 1_000, kraken: 250 };
// prettier-ignore
export const GLOBAL_FINANCE_DEADLINES = { boc: 12_000, eurostat: 15_000, kraken: 10_000 };

function text(value, maximum = 80) {
  return String(value ?? "").slice(0, maximum);
}

async function snapshotJson(service, request, options) {
  const response = await service.readText(request, options);
  try {
    return {
      value: JSON.parse(response.text),
      snapshot: createHash("sha256")
        .update(response.text)
        .digest("base64url")
        .slice(0, 16),
    };
  } catch {
    throw Object.assign(new Error("Financial source returned invalid JSON"), {
      status: 502,
      code: "alta_finance_invalid_response",
    });
  }
}

function requestedSnapshot(args) {
  const cursor = boundedInteger(args.cursor, 0, 0, 10_000);
  const snapshot = String(args.snapshot ?? "");
  if (snapshot && !/^[A-Za-z0-9_-]{16}$/.test(snapshot))
    throw invalid("Invalid finance snapshot token");
  if (cursor && !snapshot)
    throw invalid("A snapshot token is required after the first page");
  return snapshot;
}

function assertSnapshot(expected, actual) {
  if (expected && expected !== actual)
    throw Object.assign(
      new Error("Financial source changed; restart pagination at cursor 0"),
      { status: 409, code: "alta_finance_snapshot_changed" },
    );
}

function page(base, records, cursor, maximum, upstreamMore = false) {
  const start = boundedInteger(cursor, 0, 0, 10_000);
  const available = Math.max(0, records.length - start);
  const build = (count) => {
    const end = start + count;
    const more = end < records.length || upstreamMore;
    return {
      ...base,
      cursor: start,
      next_cursor: more ? end : null,
      truncated: more,
      records: records.slice(start, end),
    };
  };
  const empty = build(0);
  const minimal = {
    source: base.source,
    snapshot: base.snapshot,
    cursor: start,
    next_cursor: available || upstreamMore ? start + 1 : null,
    truncated: Boolean(available || upstreamMore),
    skipped_records: available ? 1 : 0,
    records: [],
  };
  if (Buffer.byteLength(JSON.stringify(empty)) > RESULT_BYTES) return minimal;
  let low = 0;
  let high = Math.min(maximum, available);
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (Buffer.byteLength(JSON.stringify(build(middle))) <= RESULT_BYTES)
      low = middle;
    else high = middle - 1;
  }
  if (!low && available) return minimal;
  return build(low);
}

async function bankOfCanada(service, args, maximum, options) {
  const expectedSnapshot = requestedSnapshot(args);
  const series = requiredText(
    args.series_id,
    "series_id",
    /^[A-Za-z0-9_,.-]{1,200}$/,
    200,
  ).toUpperCase();
  const ids = series.split(",");
  if (ids.length > 5 || ids.some((id) => id.length > 32))
    throw invalid("Bank of Canada accepts at most five bounded series IDs");
  const fromDate = isoDate(args.from_date, dateBefore(365));
  const toDate = isoDate(args.to_date, dateToday());
  assertRange(fromDate, toDate);
  const url = new URL(
    `https://www.bankofcanada.ca/valet/observations/${encodeURIComponent(series)}/json`,
  );
  url.searchParams.set("start_date", fromDate);
  url.searchParams.set("end_date", toDate);
  const { value, snapshot } = await snapshotJson(
    service,
    {
      url: url.href,
      accept: "application/json",
      max_chars: 1_000_000,
      cache_namespace: "finance-boc-valet",
      attempts: 2,
    },
    options,
  );
  assertSnapshot(expectedSnapshot, snapshot);
  const records = (value.observations ?? []).map((observation) => ({
    date: text(observation.d, 20),
    values: Object.fromEntries(
      ids.flatMap((id) =>
        observation[id]?.v === undefined
          ? []
          : [[id, text(observation[id].v, 40)]],
      ),
    ),
  }));
  return page(
    {
      source: "boc",
      series: ids,
      snapshot,
      provenance: provenance("Bank of Canada", url.href),
    },
    records,
    args.cursor,
    maximum,
  );
}

function eurostatFilters(values) {
  if (!Array.isArray(values)) return [];
  return values
    .slice(0, 12)
    .map((value) =>
      requiredText(
        value,
        "filter",
        /^[A-Za-z][A-Za-z0-9_]{0,39}=[A-Za-z0-9_.@-]{1,80}$/,
        121,
      ),
    );
}

function categoryCodes(value, dimension) {
  const index = value.dimension?.[dimension]?.category?.index;
  if (Array.isArray(index)) return index.map(String);
  return Object.entries(index ?? {})
    .sort(([, left], [, right]) => left - right)
    .map(([code]) => code);
}

function eurostatRecord(value, categories, flatIndex, observation) {
  let index = Number(flatIndex);
  const dimensions = [];
  for (let position = value.id.length - 1; position >= 0; position -= 1) {
    const size = Number(value.size[position]) || 1;
    const code = categories[position][index % size] ?? "";
    dimensions.unshift(`${text(value.id[position], 20)}=${text(code, 32)}`);
    index = Math.floor(index / size);
  }
  const status = Array.isArray(value.status)
    ? value.status[flatIndex]
    : value.status?.[flatIndex];
  return {
    dimensions: dimensions.slice(0, 6),
    dimensions_truncated: dimensions.length > 6,
    value:
      typeof observation === "number" && Number.isFinite(observation)
        ? observation
        : text(observation),
    ...(status === undefined ? {} : { status: text(status, 20) }),
  };
}

async function eurostat(service, args, maximum, options) {
  const expectedSnapshot = requestedSnapshot(args);
  const dataset = requiredText(
    args.dataset_code ?? args.dataflow,
    "dataset_code",
    /^[A-Za-z0-9_.-]{2,80}$/,
    80,
  ).toLowerCase();
  const filters = eurostatFilters(args.filters);
  const fromPeriod = optionalText(
    args.from_period,
    "from_period",
    /^.{1,10}$/,
    10,
  );
  const toPeriod = optionalText(args.to_period, "to_period", /^.{1,10}$/, 10);
  if (fromPeriod) period(fromPeriod);
  if (toPeriod) period(toPeriod);
  if (fromPeriod && toPeriod) assertPeriodRange(fromPeriod, toPeriod);
  if (!filters.length && !fromPeriod && !toPeriod)
    throw invalid("Eurostat requires a period bound or dimension filter");
  const url = new URL(
    `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/${encodeURIComponent(dataset)}`,
  );
  url.searchParams.set("format", "JSON");
  url.searchParams.set("lang", "EN");
  if (fromPeriod) url.searchParams.set("sinceTimePeriod", fromPeriod);
  if (toPeriod) url.searchParams.set("untilTimePeriod", toPeriod);
  for (const filter of filters) {
    const [name, value] = filter.split("=");
    url.searchParams.append(name, value);
  }
  const { value, snapshot } = await snapshotJson(
    service,
    {
      url: url.href,
      accept: "application/json",
      max_chars: 1_000_000,
      cache_namespace: "finance-eurostat-jsonstat",
      attempts: 1,
    },
    options,
  );
  assertSnapshot(expectedSnapshot, snapshot);
  if (
    !Array.isArray(value.id) ||
    !Array.isArray(value.size) ||
    value.id.length !== value.size.length ||
    value.id.length > 32
  )
    throw Object.assign(new Error("Eurostat returned invalid JSON-stat data"), {
      status: 502,
      code: "alta_finance_invalid_response",
    });
  const entries = Array.isArray(value.value)
    ? value.value.entries()
    : Object.entries(value.value ?? {});
  const target = boundedInteger(args.cursor, 0, 0, 10_000) + maximum + 1;
  const records = [];
  const categories = value.id.map((dimension) =>
    categoryCodes(value, dimension),
  );
  let upstreamMore = false;
  for (const [flatIndex, observation] of entries) {
    if (observation === null || observation === undefined) continue;
    if (records.length >= target) {
      upstreamMore = true;
      break;
    }
    records.push(eurostatRecord(value, categories, flatIndex, observation));
  }
  return page(
    {
      source: "eurostat",
      dataset,
      snapshot,
      label: text(value.label, 80),
      updated: text(value.updated, 40),
      provenance: provenance("Eurostat", `${url.origin}${url.pathname}`),
    },
    records,
    args.cursor,
    maximum,
    upstreamMore,
  );
}

function krakenError(value) {
  const errors = Array.isArray(value.error) ? value.error.filter(Boolean) : [];
  if (errors.length)
    throw Object.assign(new Error(text(errors.join("; "), 300)), {
      status: 502,
      code: "alta_finance_kraken_unavailable",
    });
}

async function kraken(service, args, maximum, options) {
  const expectedSnapshot = requestedSnapshot(args);
  const symbol = requiredText(
    args.symbol,
    "symbol",
    /^[A-Za-z0-9/_-]{3,32}$/,
    32,
  ).toUpperCase();
  const mode = args.market_mode === "trades" ? "trades" : "order_book";
  const endpoint = mode === "trades" ? "PostTrade" : "PreTrade";
  const url = new URL(`https://api.kraken.com/0/public/${endpoint}`);
  url.searchParams.set("symbol", symbol);
  if (mode === "trades") url.searchParams.set("count", String(maximum));
  const { value, snapshot } = await snapshotJson(
    service,
    {
      url: url.href,
      accept: "application/json",
      max_chars: 512_000,
      cache_namespace: `finance-kraken-${mode}`,
      attempts: 2,
    },
    options,
  );
  assertSnapshot(expectedSnapshot, snapshot);
  krakenError(value);
  const result = value.result ?? {};
  const records =
    mode === "trades"
      ? (result.trades ?? []).map((trade) => ({
          trade_id: text(trade.trade_id, 80),
          symbol: text(trade.symbol || symbol, 32),
          price: text(trade.price),
          quantity: text(trade.qty ?? trade.quantity),
          traded_at: text(trade.trade_ts, 40),
          published_at: text(trade.publication_ts, 40),
          venue: text(trade.trade_venue, 16),
        }))
      : [...(result.bids ?? []), ...(result.asks ?? [])].map((level) => ({
          side: text(level.side, 12),
          price: text(level.price),
          quantity: text(level.qty ?? level.quantity),
          orders: Number(level.count) || 0,
          published_at: text(level.publication_ts, 40),
        }));
  return page(
    {
      source: "kraken",
      mode,
      snapshot,
      symbol: text(result.symbol || symbol, 32),
      description: text(result.description, 120),
      provenance: provenance("Kraken", url.href),
    },
    records,
    args.cursor,
    maximum,
  );
}

export const GLOBAL_FINANCE_ADAPTERS = {
  boc: bankOfCanada,
  eurostat,
  kraken,
};
