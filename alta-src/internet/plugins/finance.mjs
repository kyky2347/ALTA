import {
  boundedInteger,
  defineTool,
  errorMessage,
  uniqueStrings,
} from "./support.mjs";
import {
  boundedRecord,
  dateBefore,
  dateToday,
  isoDate,
  provenance,
  readJson,
  requiredText,
} from "./finance-shared.mjs";
import {
  MACRO_ADAPTERS,
  MACRO_DEADLINES,
  MACRO_INTERVALS,
  MACRO_SOURCES,
} from "./finance-macro.mjs";
import {
  REGULATORY_ADAPTERS,
  REGULATORY_DEADLINES,
  REGULATORY_INTERVALS,
  REGULATORY_SOURCES,
} from "./finance-regulatory.mjs";
import {
  GLOBAL_FINANCE_ADAPTERS,
  GLOBAL_FINANCE_DEADLINES,
  GLOBAL_FINANCE_INTERVALS,
  GLOBAL_FINANCE_SOURCES,
} from "./finance-global.mjs";
import { runSource } from "./source-runtime.mjs";

const BASE_SOURCES = [
  "nasdaq",
  "coinbase",
  "worldbank",
  "treasury",
  "sec",
  "finnhub",
];
const SOURCE_NAMES = [
  ...BASE_SOURCES,
  ...MACRO_SOURCES,
  ...REGULATORY_SOURCES,
  ...GLOBAL_FINANCE_SOURCES,
];
const SOURCES = new Set(SOURCE_NAMES);
const TREASURY_DATASETS = {
  avg_interest_rates: "/v2/accounting/od/avg_interest_rates",
  debt_to_penny: "/v2/accounting/od/debt_to_penny",
};
const SOURCE_INTERVALS = {
  nasdaq: 500,
  coinbase: 100,
  worldbank: 250,
  treasury: 250,
  sec: 150,
  finnhub: 1_000,
  ...MACRO_INTERVALS,
  ...REGULATORY_INTERVALS,
  ...GLOBAL_FINANCE_INTERVALS,
};
const SOURCE_DEADLINES = {
  nasdaq: 12_000,
  coinbase: 10_000,
  worldbank: 12_000,
  treasury: 12_000,
  // A cold ticker request is deliberately sequential: official ticker mapping,
  // then submissions. Keep the pair inside one bounded but realistic deadline.
  sec: 30_000,
  finnhub: 15_000,
  ...MACRO_DEADLINES,
  ...REGULATORY_DEADLINES,
  ...GLOBAL_FINANCE_DEADLINES,
};

function nasdaqHeaders() {
  return {
    "User-Agent":
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140 Safari/537.36",
    "Referer": "https://www.nasdaq.com/",
    "Accept-Language": "en-US,en;q=0.9",
  };
}

function checkNasdaq(value) {
  if (value.status?.rCode === 200 && value.data) return value.data;
  const message = value.status?.bCodeMessage?.[0]?.errorMessage;
  throw Object.assign(new Error(message || "Nasdaq returned no public data"), {
    status: 502,
    code: "alta_finance_nasdaq_unavailable",
  });
}

async function nasdaq(service, args, maximum, options) {
  const symbol = requiredText(
    args.symbol,
    "symbol",
    /^[A-Za-z0-9.^-]{1,20}$/,
    20,
  ).toUpperCase();
  const assetClass = ["stocks", "etf", "index"].includes(args.asset_class)
    ? args.asset_class
    : "stocks";
  const fromDate = isoDate(args.from_date, dateBefore(30));
  const toDate = isoDate(args.to_date, dateToday());
  if (fromDate > toDate)
    throw Object.assign(new Error("from_date must not exceed to_date"), {
      status: 400,
      code: "alta_finance_invalid_date_range",
    });
  const infoUrl = new URL(
    `https://api.nasdaq.com/api/quote/${encodeURIComponent(symbol)}/info`,
  );
  infoUrl.searchParams.set("assetclass", assetClass);
  const historyUrl = new URL(
    `https://api.nasdaq.com/api/quote/${encodeURIComponent(symbol)}/historical`,
  );
  historyUrl.searchParams.set("assetclass", assetClass);
  historyUrl.searchParams.set("fromdate", fromDate);
  historyUrl.searchParams.set("todate", toDate);
  historyUrl.searchParams.set("limit", String(maximum));
  const requests = [infoUrl, historyUrl].map((url, index) =>
    readJson(
      service,
      {
        url: url.href,
        accept: "application/json",
        headers: nasdaqHeaders(),
        max_chars: 512_000,
        cache_namespace: index
          ? "finance-nasdaq-history"
          : "finance-nasdaq-info",
        attempts: 2,
      },
      options,
    ).then(checkNasdaq),
  );
  const [info, history] = await Promise.allSettled(requests);
  if (info.status === "rejected" && history.status === "rejected")
    throw info.reason;
  const primary = info.status === "fulfilled" ? info.value.primaryData : null;
  const rows =
    history.status === "fulfilled"
      ? (history.value.tradesTable?.rows ?? []).slice(0, maximum)
      : [];
  return {
    source: "nasdaq",
    symbol,
    asset_class: assetClass,
    quote: primary
      ? {
          price: primary.lastSalePrice,
          change: primary.netChange,
          change_percent: primary.percentageChange,
          volume: primary.volume,
          timestamp: primary.lastTradeTimestamp,
          realtime: primary.isRealTime,
        }
      : null,
    history: rows.map((row) => ({
      date: row.date,
      close: row.close,
      volume: row.volume,
      open: row.open,
      high: row.high,
      low: row.low,
    })),
    failures: [
      ...(info.status === "rejected"
        ? [{ endpoint: "quote", error: errorMessage(info.reason) }]
        : []),
      ...(history.status === "rejected"
        ? [{ endpoint: "history", error: errorMessage(history.reason) }]
        : []),
    ],
    partial: info.status === "rejected" || history.status === "rejected",
    provenance: provenance("Nasdaq", infoUrl.href),
  };
}

async function coinbase(service, args, maximum, options) {
  const product = requiredText(
    args.product ?? args.symbol,
    "product",
    /^[A-Za-z0-9]{2,15}-[A-Za-z0-9]{2,15}$/,
    31,
  ).toUpperCase();
  const granularity = boundedInteger(args.granularity, 86_400, 60, 86_400);
  if (![60, 300, 900, 3_600, 21_600, 86_400].includes(granularity))
    throw Object.assign(new Error("Unsupported Coinbase granularity"), {
      status: 400,
      code: "alta_finance_invalid_granularity",
    });
  const end = Math.floor(Date.now() / 1000);
  const start = end - granularity * maximum;
  const tickerUrl = `https://api.exchange.coinbase.com/products/${encodeURIComponent(product)}/ticker`;
  const candlesUrl = new URL(
    `https://api.exchange.coinbase.com/products/${encodeURIComponent(product)}/candles`,
  );
  candlesUrl.searchParams.set("granularity", String(granularity));
  candlesUrl.searchParams.set("start", new Date(start * 1000).toISOString());
  candlesUrl.searchParams.set("end", new Date(end * 1000).toISOString());
  const [ticker, candles] = await Promise.all([
    readJson(
      service,
      {
        url: tickerUrl,
        accept: "application/json",
        max_chars: 64_000,
        cache_namespace: "finance-coinbase-ticker",
        attempts: 2,
      },
      options,
    ),
    readJson(
      service,
      {
        url: candlesUrl.href,
        accept: "application/json",
        max_chars: 256_000,
        cache_namespace: "finance-coinbase-candles",
        attempts: 2,
      },
      options,
    ),
  ]);
  return {
    source: "coinbase",
    product,
    quote: {
      price: ticker.price,
      bid: ticker.bid,
      ask: ticker.ask,
      volume: ticker.volume,
      time: ticker.time,
    },
    granularity_seconds: granularity,
    candles: candles.slice(0, maximum).map((row) => ({
      time: new Date(row[0] * 1000).toISOString(),
      low: row[1],
      high: row[2],
      open: row[3],
      close: row[4],
      volume: row[5],
    })),
    provenance: provenance("Coinbase Exchange", tickerUrl),
  };
}

function year(value, fallback) {
  return boundedInteger(value, fallback, 1960, 2100);
}

async function worldBank(service, args, maximum, options) {
  const country = requiredText(
    args.country,
    "country",
    /^[A-Za-z0-9;]{2,80}$/,
    80,
  );
  const indicator = requiredText(
    args.indicator,
    "indicator",
    /^[A-Za-z0-9.;]{2,100}$/,
    100,
  );
  const fromYear = year(args.from_year, 2015);
  const toYear = year(args.to_year, new Date().getUTCFullYear());
  if (fromYear > toYear)
    throw Object.assign(new Error("from_year must not exceed to_year"), {
      status: 400,
      code: "alta_finance_invalid_year_range",
    });
  const url = new URL(
    `https://api.worldbank.org/v2/country/${country}/indicator/${indicator}`,
  );
  url.searchParams.set("format", "json");
  url.searchParams.set("date", `${fromYear}:${toYear}`);
  url.searchParams.set("per_page", String(maximum));
  const value = await readJson(
    service,
    {
      url: url.href,
      accept: "application/json",
      max_chars: 512_000,
      cache_namespace: "finance-worldbank",
      attempts: 2,
    },
    options,
  );
  return {
    source: "worldbank",
    country,
    indicator,
    metadata: value[0] ?? {},
    observations: (value[1] ?? []).slice(0, maximum).map((item) => ({
      country: item.country?.value,
      country_code: item.countryiso3code,
      indicator: item.indicator?.value,
      date: item.date,
      value: item.value,
      unit: item.unit,
      status: item.obs_status,
    })),
    provenance: provenance("World Bank", url.href),
  };
}

async function treasury(service, args, maximum, options) {
  const dataset = TREASURY_DATASETS[args.dataset]
    ? args.dataset
    : "avg_interest_rates";
  const url = new URL(
    `https://api.fiscaldata.treasury.gov/services/api/fiscal_service${TREASURY_DATASETS[dataset]}`,
  );
  url.searchParams.set("page[size]", String(maximum));
  url.searchParams.set("sort", "-record_date");
  const filters = [];
  if (args.from_date)
    filters.push(`record_date:gte:${isoDate(args.from_date, "")}`);
  if (args.to_date)
    filters.push(`record_date:lte:${isoDate(args.to_date, "")}`);
  if (filters.length) url.searchParams.set("filter", filters.join(","));
  const value = await readJson(
    service,
    {
      url: url.href,
      accept: "application/json",
      max_chars: 512_000,
      cache_namespace: "finance-treasury",
      attempts: 2,
    },
    options,
  );
  return {
    source: "treasury",
    dataset,
    records: (value.data ?? []).slice(0, maximum),
    metadata: value.meta ?? {},
    provenance: provenance("U.S. Department of the Treasury", url.href),
  };
}

async function secIdentity(service, args, options) {
  if (args.cik) {
    return {
      cik: requiredText(args.cik, "cik", /^\d{1,10}$/, 10).padStart(10, "0"),
      resolved_from: "cik",
    };
  }
  const symbol = requiredText(
    args.symbol,
    "symbol or cik",
    /^[A-Za-z0-9.^-]{1,20}$/,
    20,
  ).toUpperCase();
  const mappingUrl = "https://www.sec.gov/files/company_tickers_exchange.json";
  const mapping = await readJson(
    service,
    {
      url: mappingUrl,
      accept: "application/json",
      headers: { "User-Agent": service.secUserAgent },
      max_chars: 2_000_000,
      cache_namespace: "finance-sec-ticker-map",
      attempts: 1,
    },
    options,
  );
  const fields = Array.isArray(mapping.fields) ? mapping.fields : [];
  const rows = Array.isArray(mapping.data) ? mapping.data : [];
  const cikIndex = fields.indexOf("cik");
  const nameIndex = fields.indexOf("name");
  const tickerIndex = fields.indexOf("ticker");
  const exchangeIndex = fields.indexOf("exchange");
  const match = rows.find(
    (row) =>
      Array.isArray(row) &&
      tickerIndex >= 0 &&
      String(row[tickerIndex] ?? "").toUpperCase() === symbol,
  );
  if (!match || cikIndex < 0)
    throw Object.assign(
      new Error(`SEC ticker mapping has no ${symbol} entry`),
      {
        status: 404,
        code: "alta_finance_sec_symbol_not_found",
      },
    );
  const cik = String(match[cikIndex] ?? "").replace(/\D/g, "");
  if (!cik)
    throw Object.assign(
      new Error(`SEC ticker mapping has no CIK for ${symbol}`),
      {
        status: 502,
        code: "alta_finance_sec_mapping_invalid",
      },
    );
  return {
    cik: cik.padStart(10, "0"),
    symbol,
    company: nameIndex >= 0 ? match[nameIndex] : undefined,
    exchange: exchangeIndex >= 0 ? match[exchangeIndex] : undefined,
    resolved_from: "symbol",
    mapping_url: mappingUrl,
  };
}

async function sec(service, args, maximum, options) {
  const identity = await secIdentity(service, args, options);
  const { cik } = identity;
  const forms = uniqueStrings(args.forms, 10, 20).map((form) =>
    form.toUpperCase(),
  );
  const sourceUrl = `https://data.sec.gov/submissions/CIK${cik}.json`;
  const value = await readJson(
    service,
    {
      url: sourceUrl,
      accept: "application/json",
      headers: { "User-Agent": service.secUserAgent },
      max_chars: 1_000_000,
      cache_namespace: "finance-sec-submissions",
      attempts: 1,
    },
    options,
  );
  const recent = value.filings?.recent ?? {};
  const filings = (recent.accessionNumber ?? [])
    .map((accession, index) => ({
      accession,
      form: recent.form?.[index],
      filed_at: recent.filingDate?.[index],
      report_date: recent.reportDate?.[index],
      primary_document: recent.primaryDocument?.[index],
      description: recent.primaryDocDescription?.[index],
    }))
    .filter((filing) => !forms.length || forms.includes(filing.form))
    .slice(0, maximum)
    .map((filing) => ({
      ...filing,
      url: `https://www.sec.gov/Archives/edgar/data/${Number(cik)}/${filing.accession.replaceAll("-", "")}/${filing.primary_document}`,
    }));
  return {
    source: "sec",
    cik,
    requested_symbol: identity.symbol,
    resolved_from: identity.resolved_from,
    company: value.name,
    tickers: value.tickers ?? [],
    exchanges: value.exchanges ?? [],
    filings,
    provenance: provenance(
      "U.S. Securities and Exchange Commission",
      sourceUrl,
    ),
    identity_provenance:
      identity.resolved_from === "symbol"
        ? provenance(
            "U.S. Securities and Exchange Commission",
            identity.mapping_url,
          )
        : undefined,
  };
}

const FINNHUB_DATASETS = new Set([
  "company_news",
  "earnings_calendar",
  "insider_transactions",
  "peers",
  "metrics",
  "recommendations",
]);

const FINNHUB_FIELDS = {
  company_news: [
    "category",
    "datetime",
    "headline",
    "id",
    "image",
    "related",
    "source",
    "summary",
    "url",
  ],
  earnings_calendar: [
    "date",
    "epsActual",
    "epsEstimate",
    "hour",
    "quarter",
    "revenueActual",
    "revenueEstimate",
    "symbol",
    "year",
  ],
  insider_transactions: [
    "change",
    "filingDate",
    "name",
    "share",
    "symbol",
    "transactionCode",
    "transactionDate",
    "transactionPrice",
  ],
  metrics: ["metric", "series", "symbol"],
  recommendations: [
    "buy",
    "hold",
    "period",
    "sell",
    "strongBuy",
    "strongSell",
    "symbol",
  ],
};

function finnhubRecords(dataset, value, maximum) {
  if (dataset === "peers")
    return (Array.isArray(value) ? value : [])
      .slice(0, maximum)
      .map((symbol) => ({ symbol: String(symbol).slice(0, 20) }));
  const rows =
    dataset === "earnings_calendar"
      ? value.earningsCalendar
      : dataset === "insider_transactions"
        ? value.data
        : dataset === "metrics"
          ? [value]
          : value;
  return (Array.isArray(rows) ? rows : [])
    .slice(0, maximum)
    .map((row) => boundedRecord(row, FINNHUB_FIELDS[dataset] ?? [], 1_000));
}

async function finnhub(service, args, maximum, options) {
  if (!service.finnhubKey)
    throw Object.assign(
      new Error(
        "Finnhub credential is not configured in the external ALTA credential store",
      ),
      { status: 503, code: "alta_finance_finnhub_credential_missing" },
    );
  const dataset = FINNHUB_DATASETS.has(args.dataset)
    ? args.dataset
    : "company_news";
  const symbol = requiredText(
    args.symbol,
    "symbol",
    /^[A-Za-z0-9.^-]{1,20}$/,
    20,
  ).toUpperCase();
  const fromDate = isoDate(args.from_date, dateBefore(30));
  const toDate = isoDate(args.to_date, dateToday());
  if (fromDate > toDate)
    throw Object.assign(new Error("from_date must not exceed to_date"), {
      status: 400,
      code: "alta_finance_invalid_date_range",
    });
  const endpoints = {
    company_news: "/api/v1/company-news",
    earnings_calendar: "/api/v1/calendar/earnings",
    insider_transactions: "/api/v1/stock/insider-transactions",
    peers: "/api/v1/stock/peers",
    metrics: "/api/v1/stock/metric",
    recommendations: "/api/v1/stock/recommendation",
  };
  const url = new URL(endpoints[dataset], "https://finnhub.io");
  url.searchParams.set("symbol", symbol);
  if (
    ["company_news", "earnings_calendar", "insider_transactions"].includes(
      dataset,
    )
  ) {
    url.searchParams.set("from", fromDate);
    url.searchParams.set("to", toDate);
  }
  if (dataset === "metrics") url.searchParams.set("metric", "all");
  url.searchParams.set("token", service.finnhubKey);
  const value = await readJson(
    service,
    {
      url: url.href,
      accept: "application/json",
      max_chars: 768_000,
      cache_namespace: `finance-finnhub-${dataset}`,
      attempts: 2,
    },
    options,
  );
  const sourceUrl = new URL(url);
  sourceUrl.searchParams.delete("token");
  return {
    source: "finnhub",
    dataset,
    symbol,
    records: finnhubRecords(dataset, value, maximum),
    provenance: {
      publisher: "Finnhub",
      source_url: sourceUrl.href,
      official: true,
      authentication: "api_key",
    },
  };
}

const ADAPTERS = {
  nasdaq,
  coinbase,
  worldbank: worldBank,
  treasury,
  sec,
  finnhub,
  ...MACRO_ADAPTERS,
  ...REGULATORY_ADAPTERS,
  ...GLOBAL_FINANCE_ADAPTERS,
};

async function financeData(service, args, options) {
  const source = String(args.source ?? "").toLowerCase();
  if (!SOURCES.has(source))
    throw Object.assign(new Error("Unsupported or missing finance source"), {
      status: 400,
      code: "alta_finance_invalid_source",
    });
  const maximum = boundedInteger(args.max_records, 20, 1, 50);
  try {
    return await runSource(
      service,
      "finance",
      source,
      options,
      (sourceOptions) =>
        ADAPTERS[source](service, args, maximum, sourceOptions),
      {
        intervalMs: SOURCE_INTERVALS[source],
        deadlineMs: SOURCE_DEADLINES[source],
      },
    );
  } catch (error) {
    if (
      !["sec", "sec_xbrl"].includes(source) ||
      error.status === 400 ||
      options?.signal?.aborted
    )
      throw error;
    const cikDigits = String(args.cik ?? "")
      .replace(/\D/g, "")
      .slice(0, 10);
    const cik = cikDigits ? cikDigits.padStart(10, "0") : "";
    const symbol = String(args.symbol ?? "")
      .replace(/[^A-Za-z0-9.^-]/g, "")
      .slice(0, 20)
      .toUpperCase();
    const forms = uniqueStrings(args.forms, 10, 20).join(" OR ");
    const xbrl = [args.taxonomy, args.concept, args.xbrl_period]
      .filter(Boolean)
      .join(" ");
    const fallback = await service.search(
      {
        query: `SEC EDGAR${symbol ? ` ${symbol}` : ""}${cik ? ` CIK ${cik}` : ""}${forms ? ` (${forms})` : ""}${xbrl ? ` ${xbrl}` : ""}`,
        allowed_domains: ["sec.gov"],
        max_results: maximum,
        depth: "quick",
        backend: "auto",
      },
      options,
    );
    return {
      source,
      cik,
      ...(symbol ? { symbol } : {}),
      ...(source === "sec" ? { filings: [] } : { facts: [] }),
      fallback_results: (fallback.results ?? []).map((item) => ({
        title: item.title,
        url: item.url,
        snippets: item.snippets,
      })),
      failures: [{ endpoint: "data.sec.gov", error: errorMessage(error) }],
      partial: true,
    };
  }
}

export const financePlugin = {
  id: "alta-public-finance-data",
  tools: [
    defineTool(
      "alta_finance_data",
      "ALTA Public Finance Data",
      "Query 17 login-free public sources plus authenticated Finnhub company intelligence for markets, macro, positioning, filings, events, peers, and fundamentals. Returns bounded provenance; not financial advice.",
      {
        type: "object",
        properties: {
          source: {
            type: "string",
            enum: SOURCE_NAMES,
            description:
              "Markets: nasdaq/coinbase/kraken; company intelligence: finnhub; macro: fred/bls/worldbank/imf/oecd/eurostat; rates/FX: nyfed/ecb/boc; fiscal: treasury; regulatory: fdic/cftc/sec/sec_xbrl.",
          },
          symbol: { type: "string" },
          product: { type: "string" },
          asset_class: {
            type: "string",
            enum: ["stocks", "etf", "index"],
          },
          granularity: {
            type: "integer",
            enum: [60, 300, 900, 3600, 21600, 86400],
          },
          country: { type: "string" },
          countries: {
            type: "array",
            maxItems: 10,
            items: { type: "string" },
          },
          indicator: { type: "string" },
          series_id: { type: "string" },
          dataset_code: {
            type: "string",
            description: "Eurostat dataset code.",
          },
          filters: {
            type: "array",
            maxItems: 12,
            items: { type: "string" },
            description: "Eurostat dimension=value filters.",
          },
          cursor: {
            type: "integer",
            minimum: 0,
            maximum: 10000,
            description: "Continuation cursor; also pass the prior snapshot.",
          },
          snapshot: {
            type: "string",
            description: "Snapshot token returned with the preceding page.",
          },
          market_mode: {
            type: "string",
            enum: ["order_book", "trades"],
          },
          from_year: { type: "integer", minimum: 1800, maximum: 2200 },
          to_year: { type: "integer", minimum: 1800, maximum: 2200 },
          dataset: {
            type: "string",
            enum: [
              "avg_interest_rates",
              "debt_to_penny",
              "institutions",
              "financials",
              "failures",
              "summary",
              "company_news",
              "earnings_calendar",
              "insider_transactions",
              "peers",
              "metrics",
              "recommendations",
            ],
          },
          rate_type: {
            type: "string",
            enum: ["all", "tgcr", "bgcr", "sofr", "sofrai", "effr", "obfr"],
          },
          dataflow: { type: "string" },
          key: { type: "string" },
          from_period: { type: "string" },
          to_period: { type: "string" },
          cik: {
            type: "string",
            description:
              "SEC CIK. For source=sec, pass either cik or symbol; ticker resolution uses the official SEC mapping.",
          },
          forms: {
            type: "array",
            maxItems: 10,
            items: { type: "string" },
          },
          xbrl_mode: {
            type: "string",
            enum: ["company_concept", "frame"],
          },
          taxonomy: { type: "string" },
          concept: { type: "string" },
          unit: { type: "string" },
          xbrl_period: { type: "string" },
          fdic_filter: { type: "string" },
          fields: {
            type: "array",
            maxItems: 20,
            items: { type: "string" },
          },
          cftc_report: {
            type: "string",
            enum: [
              "legacy_futures",
              "legacy_combined",
              "disaggregated_futures",
              "tff_futures",
            ],
          },
          market: { type: "string" },
          from_date: { type: "string" },
          to_date: { type: "string" },
          max_records: { type: "integer", minimum: 1, maximum: 50 },
        },
        required: ["source"],
        additionalProperties: false,
      },
      financeData,
    ),
  ],
};
