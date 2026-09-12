import { boundedInteger, defineTool, uniqueStrings } from "./support.mjs";
import { settleSources } from "./source-runtime.mjs";
import {
  cleanSocial,
  DIRECT_SOCIAL_PLATFORMS,
  searchDirectSocial,
} from "./social-sources.mjs";
import {
  configuredSocialDomains,
  PLATFORM_DOMAINS,
  platformForUrl,
} from "./social-platforms.mjs";
import { readPublicSocialUrl } from "./social-read.mjs";
const DEFAULT_PLATFORMS = [
  "bluesky",
  "hackernews",
  "lemmy",
  "reddit",
  "stackexchange",
  "peertube",
  "youtube",
  "x",
];

function chunks(values, size) {
  return Array.from({ length: Math.ceil(values.length / size) }, (_, index) =>
    values.slice(index * size, (index + 1) * size),
  );
}

function mergeResults(values, maximum) {
  const merged = new Map();
  for (let index = 0; merged.size < maximum; index += 1) {
    let found = false;
    for (const results of values) {
      const item = results[index];
      if (!item?.url) continue;
      found = true;
      let key = item.url;
      try {
        const url = new URL(item.url);
        url.hash = "";
        key = url.href;
        item.url = key;
      } catch {}
      const previous = merged.get(key);
      if (!previous) merged.set(key, { ...item, providers: [item.provider] });
      else
        previous.providers = [
          ...new Set([...previous.providers, item.provider]),
        ];
      if (merged.size >= maximum) break;
    }
    if (!found) break;
  }
  return [...merged.values()];
}

async function socialSearch(service, args, options) {
  const query = String(args.query ?? "").trim();
  if (!query || query.length > 300)
    throw Object.assign(new Error("query must contain 1-300 characters"), {
      status: 400,
      code: "alta_social_invalid_query",
    });
  const requested = uniqueStrings(args.platforms, 12, 30);
  const platforms = requested.length ? requested : DEFAULT_PLATFORMS;
  if (platforms.some((platform) => !PLATFORM_DOMAINS[platform]))
    throw Object.assign(new Error("Unsupported social platform"), {
      status: 400,
      code: "alta_social_invalid_platform",
    });
  const maximum = boundedInteger(args.max_results, 15, 1, 20);
  const sort = args.sort === "latest" ? "latest" : "relevance";
  const symbol = String(args.symbol ?? "")
    .trim()
    .replace(/^\$/, "")
    .toUpperCase();
  if (symbol && !/^[A-Z][A-Z0-9.-]{0,14}$/.test(symbol))
    throw Object.assign(new Error("symbol must be a valid market symbol"), {
      status: 400,
      code: "alta_social_invalid_symbol",
    });
  const hashtag = String(args.hashtag ?? "")
    .trim()
    .replace(/^#/, "")
    .slice(0, 64);
  if (hashtag && !/^[\p{L}\p{N}_]+$/u.test(hashtag))
    throw Object.assign(
      new Error("hashtag may contain only letters, numbers, and underscores"),
      { status: 400, code: "alta_social_invalid_hashtag" },
    );
  const directPlatforms = platforms.filter(
    (platform) =>
      DIRECT_SOCIAL_PLATFORMS.has(platform) &&
      (platform !== "stocktwits" || symbol),
  );
  const tasks = {};
  for (const platform of directPlatforms) {
    if (platform === "mastodon" && !hashtag) continue;
    tasks[platform] = (sourceOptions) =>
      searchDirectSocial(
        service,
        platform,
        {
          query,
          maximum,
          sort,
          hashtag,
          symbol,
          stackexchangeSite: args.stackexchange_site,
        },
        sourceOptions,
      );
  }
  const discoveryPlatforms = platforms.filter(
    (platform) =>
      args.web_fallback === true ||
      platform === "youtube" ||
      platform === "stocktwits" ||
      !directPlatforms.includes(platform),
  );
  const domains = configuredSocialDomains(service, discoveryPlatforms);
  chunks(domains, 5).forEach((allowedDomains, index) => {
    tasks[`web-${index + 1}`] = async (sourceOptions) => {
      const value = await service.search(
        {
          query,
          allowed_domains: allowedDomains,
          max_results: maximum,
          depth: "quick",
          backend: args.backend ?? "auto",
        },
        sourceOptions,
      );
      return (value.results ?? []).map((item) => ({
        platform: platformForUrl(item.url),
        url: item.url,
        author: "",
        title: cleanSocial(item.title, 500),
        content: cleanSocial((item.snippets ?? []).join(" ")),
        published_at: "",
        metrics: {},
        provider: `web-${value.backend}`,
      }));
    };
  });
  const sources = Object.keys(tasks);
  const intervals = {
    bluesky: 250,
    hackernews: 100,
    lemmy: 250,
    mastodon: 500,
    reddit: 1_000,
    stackexchange: 250,
    peertube: 500,
    devto: 500,
    discourse: 500,
    youtube: 1_000,
    stocktwits: 2_000,
    ...Object.fromEntries(
      sources
        .filter((source) => source.startsWith("web-"))
        .map((source) => [source, 250]),
    ),
  };
  const settled = await settleSources(
    service,
    "social",
    sources,
    options,
    (source, sourceOptions) => tasks[source](sourceOptions),
    {
      intervals,
      deadlines: Object.fromEntries(sources.map((source) => [source, 10_000])),
    },
  );
  const results = mergeResults(
    settled.values.map(({ value }) => value),
    maximum,
  );
  return {
    query,
    platforms,
    sources: settled.values.map(({ source }) => source),
    results,
    result_count: results.length,
    failures: settled.failures,
    partial: settled.failures.length > 0,
  };
}

export const socialPlugin = {
  id: "alta-public-social-discovery",
  tools: [
    defineTool(
      "alta_social_search",
      "ALTA Public Social Search",
      "Search public social content through eleven direct sources and bounded discovery across 48 platforms. Use alta_social_read on returned public URLs. Social content is a lead, not independent confirmation; never bypass access controls.",
      {
        type: "object",
        properties: {
          query: {
            type: "string",
            description: "Search terms, limited to 300 characters.",
          },
          platforms: {
            type: "array",
            maxItems: 12,
            items: { type: "string", enum: Object.keys(PLATFORM_DOMAINS) },
            description:
              "Optional platforms. Direct public APIs are used where available; the rest use restricted-domain web discovery.",
          },
          hashtag: {
            type: "string",
            description:
              "Optional Mastodon hashtag without spaces; enables its public hashtag API.",
          },
          stackexchange_site: {
            type: "string",
            description:
              "Optional Stack Exchange API site, such as stackoverflow, superuser, or askubuntu.",
          },
          symbol: {
            type: "string",
            description: "Optional Stocktwits ticker, such as AAPL or BTC.X.",
          },
          sort: {
            type: "string",
            enum: ["relevance", "latest"],
            description:
              "Sort hint for direct sources; restricted web sources retain their backend ranking.",
          },
          backend: {
            type: "string",
            default: "auto",
            description:
              "ALTA web-search backend used for platforms without a direct public adapter.",
          },
          web_fallback: {
            type: "boolean",
            description:
              "Also run domain discovery for direct-API platforms. Defaults to false to minimize latency and outbound requests.",
          },
          max_results: { type: "integer", minimum: 1, maximum: 20 },
        },
        required: ["query"],
        additionalProperties: false,
      },
      socialSearch,
    ),
    defineTool(
      "alta_social_read",
      "ALTA Public Social Read",
      "Read a compact preview of one public social or forum URL without credentials. Uses public oEmbed or bounded page extraction; TradingView is display-only and must use alta_tradingview_navigate. Never bypasses access controls.",
      {
        type: "object",
        properties: {
          url: { type: "string" },
          max_chars: { type: "integer", minimum: 1_000, maximum: 4_000 },
        },
        required: ["url"],
        additionalProperties: false,
      },
      readPublicSocialUrl,
    ),
  ],
};
