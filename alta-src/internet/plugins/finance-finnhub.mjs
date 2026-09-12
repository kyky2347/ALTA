import {
  boundedRecord,
  dateBefore,
  dateToday,
  isoDate,
  readJsonResult,
  requiredText,
} from "./finance-shared.mjs";

const FINNHUB_DATASETS = new Set([
  "company_news",
  "company_profile",
  "earnings_surprises",
  "earnings_calendar",
  "insider_transactions",
  "peers",
  "metrics",
  "recommendations",
]);

const FINNHUB_FIELDS = {
  company_profile: [
    "name",
    "ticker",
    "weburl",
    "country",
    "currency",
    "exchange",
    "finnhubIndustry",
    "ipo",
    "marketCapitalization",
    "shareOutstanding",
  ],
  earnings_surprises: [
    "actual",
    "estimate",
    "period",
    "quarter",
    "surprise",
    "surprisePercent",
    "symbol",
    "year",
  ],
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
  // The basic-metrics endpoint also returns decades of nested series. Sending
  // that history for a metric request obscures both current values and provenance.
  metrics: ["metric", "symbol"],
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
        : ["metrics", "company_profile"].includes(dataset)
          ? [value]
          : value;
  return (Array.isArray(rows) ? rows : [])
    .slice(0, maximum)
    .map((row) => boundedRecord(row, FINNHUB_FIELDS[dataset] ?? [], 1_000));
}

export async function finnhub(service, args, maximum, options) {
  if (!service.finnhubKey)
    throw Object.assign(
      new Error(
        "Finnhub credential is not configured in the external ALTA credential store",
      ),
      { status: 503, code: "alta_finance_finnhub_credential_missing" },
    );
  const dataset = args.dataset ?? "company_news";
  if (!FINNHUB_DATASETS.has(dataset))
    throw Object.assign(new Error("Unsupported Finnhub dataset"), {
      status: 400,
      code: "alta_finance_invalid_dataset",
    });
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
    company_profile: "/api/v1/stock/profile2",
    earnings_surprises: "/api/v1/stock/earnings",
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
  if (dataset === "earnings_surprises")
    url.searchParams.set("limit", String(maximum));
  url.searchParams.set("token", service.finnhubKey);
  const { value, status } = await readJsonResult(
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
  const expectsObject = [
    "metrics",
    "company_profile",
    "earnings_calendar",
    "insider_transactions",
  ].includes(dataset);
  if (
    !value ||
    (expectsObject
      ? typeof value !== "object" || Array.isArray(value)
      : !Array.isArray(value)) ||
    value.error
  )
    throw Object.assign(
      new Error("Finnhub returned an invalid dataset response"),
      {
        status: 502,
        code: "alta_finance_invalid_response",
      },
    );
  const records = finnhubRecords(dataset, value, maximum).filter(
    (row) => Object.keys(row).length,
  );
  // A fiscal period is not an announcement timestamp, and a newly fetched
  // historic surprise is not a new event or a current consensus estimate.
  const interpretation =
    dataset === "earnings_surprises"
      ? "Historical reported EPS versus provider estimates. period is the fiscal period, not publication time; not current consensus or point-in-time historical estimates."
      : dataset === "company_profile"
        ? "Current provider identity snapshot. weburl is a discovery locator, not retrieved issuer evidence. IPO date is not snapshot freshness."
        : undefined;
  return {
    source: "finnhub",
    dataset,
    symbol,
    records,
    ...status,
    ...(interpretation ? { interpretation } : {}),
    ...(records.length ? {} : { no_results: true }),
    provenance: {
      publisher: "Finnhub",
      source_url: sourceUrl.href,
      official: true,
      authentication: "api_key",
    },
  };
}
