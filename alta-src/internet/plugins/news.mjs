import { parseFeed } from "./discovery.mjs";
import { boundedInteger, defineTool, uniqueStrings } from "./support.mjs";
import { settleSources } from "./source-runtime.mjs";

const PUBLISHER_FEEDS = {
  bbc_world: "https://feeds.bbci.co.uk/news/world/rss.xml",
  bbc_zh: "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml",
  npr_world: "https://feeds.npr.org/1004/rss.xml",
  dw_world: "https://rss.dw.com/rdf/rss-en-all",
  dw_zh: "https://rss.dw.com/rdf/rss-chi-all",
  aljazeera: "https://www.aljazeera.com/xml/rss/all.xml",
  france24: "https://www.france24.com/en/rss",
  cbc_world: "https://www.cbc.ca/cmlink/rss-world",
  abc_australia: "https://www.abc.net.au/news/feed/51120/rss.xml",
  guardian_world: "https://www.theguardian.com/world/rss",
  sky_world: "https://feeds.skynews.com/feeds/rss/world.xml",
  rfi_zh: "https://www.rfi.fr/cn/rss",
  cna: "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml",
};
const SOURCES = new Set([
  "gdelt",
  "google_news",
  "bing_news",
  "wikinews",
  "official_finance",
  "official_global",
  "official_policy",
  ...Object.keys(PUBLISHER_FEEDS),
]);
const DEFAULT_SOURCES = [
  "gdelt",
  "google_news",
  "bing_news",
  "official_finance",
];
const OFFICIAL_FINANCE_DOMAINS = [
  "sec.gov",
  "federalreserve.gov",
  "home.treasury.gov",
  "ecb.europa.eu",
  "worldbank.org",
];
const OFFICIAL_GLOBAL_DOMAINS = [
  "un.org",
  "who.int",
  "imf.org",
  "bis.org",
  "oecd.org",
];
const OFFICIAL_POLICY_DOMAINS = [
  "whitehouse.gov",
  "gov.uk",
  "europa.eu",
  "justice.gov",
  "iea.org",
];
const TIMESPANS = {
  "1h": { gdelt: "1hour", google: "1h", freshness: "day", days: 1 / 24 },
  "6h": { gdelt: "6hours", google: "6h", freshness: "day", days: 0.25 },
  "1d": { gdelt: "1day", google: "1d", freshness: "day", days: 1 },
  "3d": { gdelt: "3days", google: "3d", freshness: "month", days: 3 },
  "1w": { gdelt: "1week", google: "7d", freshness: "month", days: 7 },
  "1m": { gdelt: "1month", google: "30d", freshness: "month", days: 31 },
  "3m": { gdelt: "3months", google: "90d", freshness: "year", days: 93 },
};
const NEWS_STOPWORDS = new Set([
  "the",
  "and",
  "for",
  "with",
  "from",
  "that",
  "this",
  "what",
  "when",
  "where",
  "why",
  "how",
  "news",
  "latest",
]);

function queryText(args, syntax) {
  const domains = uniqueStrings(args.domains, 5, 100);
  if (!domains.length) return args.query;
  const clauses = domains.map((domain) => `${syntax}:${domain}`);
  return `${args.query} (${clauses.join(" OR ")})`;
}

function clean(value, maximum = 1_500) {
  return String(value ?? "")
    .replace(/<[^>]*>/g, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maximum);
}

function withinTimespan(published, timespan) {
  const timestamp = Date.parse(published);
  return (
    Number.isNaN(timestamp) ||
    timestamp >= Date.now() - TIMESPANS[timespan].days * 86_400_000
  );
}

async function gdelt(service, args, maximum, options) {
  const url = new URL("https://api.gdeltproject.org/api/v2/doc/doc");
  url.searchParams.set("query", queryText(args, "domain"));
  url.searchParams.set("mode", "artlist");
  url.searchParams.set("format", "json");
  url.searchParams.set("sort", "datedesc");
  url.searchParams.set("maxrecords", String(maximum));
  url.searchParams.set("timespan", TIMESPANS[args.timespan].gdelt);
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/json",
      max_chars: 512_000,
      cache_namespace: "news-gdelt",
      attempts: 1,
    },
    options,
  );
  return (JSON.parse(response.text).articles ?? []).map((article) => ({
    title: clean(article.title, 500),
    url: article.url,
    publisher: article.domain ?? "",
    published_at: article.seendate ?? "",
    language: article.language ?? "",
    source_country: article.sourcecountry ?? "",
    image_url: article.socialimage ?? "",
    source: "gdelt",
  }));
}

async function googleNews(service, args, maximum, options) {
  const url = new URL("https://news.google.com/rss/search");
  url.searchParams.set(
    "q",
    `${queryText(args, "site")} when:${TIMESPANS[args.timespan].google}`,
  );
  url.searchParams.set("hl", args.language);
  url.searchParams.set("gl", args.country);
  url.searchParams.set(
    "ceid",
    `${args.country}:${args.language.split("-")[0]}`,
  );
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/rss+xml,application/xml,text/xml",
      max_chars: 512_000,
      cache_namespace: "news-google",
      attempts: 2,
    },
    options,
  );
  return parseFeed(response.text, response.url, maximum).map((item) => ({
    title: item.title,
    url: item.url,
    publisher: item.author,
    published_at: item.published,
    summary: item.summary,
    source: "google_news",
  }));
}

async function bingNews(service, args, maximum, options) {
  const url = new URL("https://www.bing.com/news/search");
  url.searchParams.set("q", queryText(args, "site"));
  url.searchParams.set("format", "rss");
  url.searchParams.set("setlang", args.language.toLowerCase());
  url.searchParams.set("cc", args.country.toLowerCase());
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/rss+xml,application/xml,text/xml",
      max_chars: 512_000,
      cache_namespace: "news-bing",
      attempts: 1,
    },
    options,
  );
  return parseFeed(response.text, response.url, maximum)
    .filter((item) => withinTimespan(item.published, args.timespan))
    .map((item) => ({
      title: item.title,
      url: item.url,
      publisher: item.author,
      published_at: item.published,
      summary: item.summary,
      source: "bing_news",
    }));
}

async function wikinews(service, args, maximum, options) {
  const language = args.language.split("-")[0];
  const origin = `https://${language}.wikinews.org`;
  const url = new URL("/w/api.php", origin);
  url.searchParams.set("action", "query");
  url.searchParams.set("list", "search");
  url.searchParams.set("srsearch", args.query);
  url.searchParams.set("srlimit", String(maximum));
  url.searchParams.set("format", "json");
  url.searchParams.set("origin", "*");
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/json",
      max_chars: 256_000,
      cache_namespace: "news-wikinews",
      attempts: 2,
    },
    options,
  );
  return (JSON.parse(response.text).query?.search ?? [])
    .filter((item) => withinTimespan(item.timestamp, args.timespan))
    .map((item) => ({
      title: clean(item.title, 500),
      url: new URL(
        `/wiki/${encodeURIComponent(item.title.replaceAll(" ", "_"))}`,
        origin,
      ).href,
      publisher: `${language}.wikinews.org`,
      published_at: item.timestamp ?? "",
      summary: clean(item.snippet),
      source: "wikinews",
    }));
}

function newsTokens(query) {
  return [
    ...new Set(
      query
        .toLocaleLowerCase()
        .match(/[\p{L}\p{N}][\p{L}\p{N}_-]*/gu)
        ?.filter((token) => token.length > 1 && !NEWS_STOPWORDS.has(token)) ??
        [],
    ),
  ].slice(0, 12);
}

async function publisherFeed(service, source, args, maximum, options) {
  const response = await service.readText(
    {
      url: PUBLISHER_FEEDS[source],
      accept: "application/rss+xml,application/xml,text/xml",
      max_chars: 256_000,
      cache_namespace: `news-publisher-${source}`,
      attempts: 2,
    },
    options,
  );
  const query = args.query.toLocaleLowerCase();
  const tokens = newsTokens(args.query);
  return parseFeed(response.text, response.url, 100)
    .filter((item) => {
      const text = `${item.title} ${item.summary}`.toLocaleLowerCase();
      return (
        withinTimespan(item.published, args.timespan) &&
        (text.includes(query) || tokens.some((token) => text.includes(token)))
      );
    })
    .slice(0, maximum)
    .map((item) => ({
      title: item.title,
      url: item.url,
      publisher: item.author || source,
      published_at: item.published,
      summary: item.summary,
      source,
    }));
}

async function officialSearch(
  service,
  args,
  maximum,
  options,
  domains,
  source,
) {
  const value = await service.search(
    {
      query: args.query,
      allowed_domains: domains,
      max_results: maximum,
      depth: "quick",
      backend: "auto",
      freshness: TIMESPANS[args.timespan].freshness,
      language: args.language,
    },
    options,
  );
  return (value.results ?? []).map((item) => ({
    title: clean(item.title, 500),
    url: item.url,
    publisher: new URL(item.url).hostname,
    published_at: "",
    summary: clean((item.snippets ?? []).join(" ")),
    source,
    search_backend: value.backend,
  }));
}

function officialFinance(service, args, maximum, options) {
  return officialSearch(
    service,
    args,
    maximum,
    options,
    OFFICIAL_FINANCE_DOMAINS,
    "official_finance",
  );
}

function officialGlobal(service, args, maximum, options) {
  return officialSearch(
    service,
    args,
    maximum,
    options,
    OFFICIAL_GLOBAL_DOMAINS,
    "official_global",
  );
}

function officialPolicy(service, args, maximum, options) {
  return officialSearch(
    service,
    args,
    maximum,
    options,
    OFFICIAL_POLICY_DOMAINS,
    "official_policy",
  );
}

const ADAPTERS = {
  gdelt,
  google_news: googleNews,
  bing_news: bingNews,
  wikinews,
  official_finance: officialFinance,
  official_global: officialGlobal,
  official_policy: officialPolicy,
};

function merge(values, maximum) {
  const results = new Map();
  for (let index = 0; results.size < maximum; index += 1) {
    let found = false;
    for (const items of values) {
      const item = items[index];
      if (!item?.url) continue;
      found = true;
      let key = item.url;
      try {
        const url = new URL(item.url);
        url.hash = "";
        key = url.href;
        item.url = key;
      } catch {}
      const previous = results.get(key);
      if (!previous) results.set(key, { ...item, sources: [item.source] });
      else previous.sources = [...new Set([...previous.sources, item.source])];
      if (results.size >= maximum) break;
    }
    if (!found) break;
  }
  return [...results.values()];
}

async function newsSearch(service, args, options) {
  const query = String(args.query ?? "").trim();
  if (!query || query.length > 400)
    throw Object.assign(new Error("query must contain 1-400 characters"), {
      status: 400,
      code: "alta_news_invalid_query",
    });
  const requested = uniqueStrings(args.sources, 8, 30);
  const sources = requested.length ? requested : DEFAULT_SOURCES;
  if (sources.some((source) => !SOURCES.has(source)))
    throw Object.assign(new Error("Unsupported news source"), {
      status: 400,
      code: "alta_news_invalid_source",
    });
  const normalized = {
    query,
    domains: args.domains,
    timespan: TIMESPANS[args.timespan] ? args.timespan : "1d",
    language: /^[a-z]{2}(?:-[A-Z]{2})?$/.test(args.language)
      ? args.language
      : "en-US",
    country: /^[A-Z]{2}$/.test(args.country) ? args.country : "US",
  };
  const maximum = boundedInteger(args.max_results, 15, 1, 20);
  const intervals = Object.fromEntries(
    sources.map((source) => [
      source,
      source === "gdelt" ? 6_000 : source.startsWith("official_") ? 250 : 1_000,
    ]),
  );
  const deadlines = Object.fromEntries(
    sources.map((source) => [
      source,
      source.startsWith("official_") ? 10_000 : 8_000,
    ]),
  );
  const settled = await settleSources(
    service,
    "news",
    sources,
    options,
    (source, sourceOptions) =>
      ADAPTERS[source]
        ? ADAPTERS[source](service, normalized, maximum, sourceOptions)
        : publisherFeed(service, source, normalized, maximum, sourceOptions),
    {
      intervals,
      deadlines,
    },
  );
  const results = merge(
    settled.values.map(({ value }) => value),
    maximum,
  );
  return {
    query,
    timespan: normalized.timespan,
    sources: settled.values.map(({ source }) => source),
    results,
    result_count: results.length,
    failures: settled.failures,
    partial: settled.failures.length > 0,
  };
}

export const newsPlugin = {
  id: "alta-global-news-discovery",
  tools: [
    defineTool(
      "alta_news_search",
      "ALTA Global News Search",
      "Search login-free global news through GDELT, Google and Bing News RSS, Wikinews, primary institution domains, and thirteen official publisher feeds in English and Chinese. Sources have independent deadlines, pacing, caching, circuits, and partial-failure handling.",
      {
        type: "object",
        properties: {
          query: {
            type: "string",
            description: "News topic or event, limited to 400 characters.",
          },
          sources: {
            type: "array",
            maxItems: 8,
            items: {
              type: "string",
              enum: [...SOURCES],
            },
            description:
              "Optional sources; defaults to GDELT, Google News, Bing News, and official finance domains. Publisher feeds are opt-in to keep default latency low.",
          },
          domains: {
            type: "array",
            maxItems: 5,
            items: { type: "string" },
            description:
              "Optional publisher domains applied to GDELT, Google News, and Bing News.",
          },
          timespan: {
            type: "string",
            enum: ["1h", "6h", "1d", "3d", "1w", "1m", "3m"],
          },
          language: {
            type: "string",
            description: "Google News locale such as en-US or zh-CN.",
          },
          country: {
            type: "string",
            description: "Two-letter uppercase Google News country code.",
          },
          max_results: { type: "integer", minimum: 1, maximum: 20 },
        },
        required: ["query"],
        additionalProperties: false,
      },
      newsSearch,
    ),
  ],
};
