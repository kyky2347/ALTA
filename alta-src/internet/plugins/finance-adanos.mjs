import { invalid, isoDate, requiredText } from "./finance-shared.mjs";

export const ADANOS_DATASETS = {
  reddit_stocks: "reddit/stocks/v1/stock",
  reddit_crypto: "reddit/crypto/v1/token",
  x_stocks: "x/stocks/v1/stock",
  news_stocks: "news/stocks/v1/stock",
  polymarket_stocks: "polymarket/stocks/v1/stock",
};

export async function adanos(service, args, _maximum, options) {
  if (!service.adanosKey)
    throw Object.assign(
      new Error("Adanos operator credential is not configured"),
      {
        status: 503,
        code: "alta_finance_adanos_credential_missing",
      },
    );
  const dataset = args.dataset;
  if (!Object.hasOwn(ADANOS_DATASETS, dataset))
    throw invalid("Unsupported Adanos dataset");
  const symbol = requiredText(
    args.symbol,
    "symbol",
    /^[$A-Za-z0-9][A-Za-z0-9.$-]{0,31}$/,
    32,
  );
  const from = isoDate(args.from_date, "");
  const to = isoDate(args.to_date, "");
  if (from > to) throw invalid("from_date must not exceed to_date");
  const url = new URL(
    `https://api.adanos.org/${ADANOS_DATASETS[dataset]}/${symbol}`,
  );
  url.searchParams.set("from", from);
  url.searchParams.set("to", to);
  let data;
  try {
    const response = await service.request(url.href, {
      ...options,
      accept: "application/json",
      headers: { "X-API-Key": service.adanosKey },
      maximum: 64_000,
      attempts: 1,
    });
    data = JSON.parse(response.body);
    if (!data || typeof data !== "object" || Array.isArray(data) || data.error)
      throw new Error("Invalid provider data");
  } catch (error) {
    options?.signal?.throwIfAborted();
    throw Object.assign(
      new Error(
        "Adanos request failed; check account access, quota and provider availability",
      ),
      {
        status: error.status ?? 502,
        code: "alta_finance_adanos_unavailable",
      },
    );
  }
  return {
    source: "adanos",
    dataset,
    symbol,
    from_date: from,
    to_date: to,
    observed_at: new Date().toISOString(),
    interpretation:
      "Secondary sentiment research lead, not verified issuer evidence, prices or a trading signal; not point-in-time historical evidence. Preserve the actual retrieval time when ingesting Raw evidence.",
    provenance: {
      publisher: "Adanos",
      source_url: url.href,
      official: false,
      authentication: "api_key",
    },
    data,
  };
}
