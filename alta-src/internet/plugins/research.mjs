import {
  boundedInteger,
  defineTool,
  errorMessage,
  uniqueStrings,
} from "./support.mjs";

function compactSearch(query, value) {
  return {
    query,
    backend: value.backend,
    backends: value.backends,
    answer: String(value.answer ?? "").slice(0, 6_000),
    answers: (value.answers ?? []).map((item) => ({
      backend: item.backend,
      answer: String(item.answer ?? "").slice(0, 3_000),
    })),
    results: (value.results ?? []).map((item) => ({
      url: item.url,
      title: item.title ?? "",
      snippets: (item.snippets ?? []).map((text) => String(text).slice(0, 600)),
      backends: item.backends,
    })),
  };
}

const SEARCH_STOP_WORDS = new Set([
  "about",
  "after",
  "against",
  "before",
  "company",
  "from",
  "into",
  "latest",
  "official",
  "report",
  "research",
  "that",
  "their",
  "this",
  "versus",
  "with",
]);

function researchTerms(queries) {
  return [
    ...new Set(
      queries
        .join(" ")
        .toLowerCase()
        .match(/[a-z0-9][a-z0-9.-]{2,}/g)
        ?.filter((term) => !SEARCH_STOP_WORDS.has(term)) ?? [],
    ),
  ].slice(0, 40);
}

function domainMatches(hostname, domain) {
  const host = hostname.toLowerCase().replace(/\.$/, "");
  const expected = domain.toLowerCase().replace(/^\.+|\.$/g, "");
  return host === expected || host.endsWith(`.${expected}`);
}

function sourceQuality(source, terms, allowedDomains) {
  let url;
  try {
    url = new URL(source.url);
  } catch {
    return -100;
  }
  const corpus = [
    url.hostname,
    url.pathname,
    source.title,
    ...(source.snippets ?? []),
  ]
    .join(" ")
    .toLowerCase();
  const termMatches = terms.filter((term) => corpus.includes(term)).length;
  const allowedDomainMatch = allowedDomains.some((domain) =>
    domainMatches(url.hostname, domain),
  );
  const authority =
    url.hostname.endsWith(".gov") || url.hostname === "sec.gov"
      ? 7
      : url.hostname.endsWith(".edu")
        ? 3
        : 0;
  const primaryPath =
    /\b(investors?|investor-relations|earnings|results|filings?|press-release|newsroom|annual-report|quarterly-report|10-k|10-q)\b/i.test(
      `${url.pathname} ${source.title ?? ""}`,
    )
      ? 4
      : 0;
  const lowSignal =
    /\b(calendar|holiday|dictionary|translation|support|how-to|wikipedia)\b/i.test(
      `${url.hostname} ${url.pathname} ${source.title ?? ""}`,
    )
      ? 5
      : 0;
  return {
    score:
      Math.min(termMatches, 8) * 2 +
      Math.min((source.queries ?? []).length, 4) +
      Math.min((source.backends ?? []).length, 3) * 2 +
      authority +
      primaryPath -
      lowSignal -
      (terms.length && termMatches === 0 ? 4 : 0),
    termMatches,
    allowedDomainMatch,
  };
}

function rankSources(sources, queries, allowedDomains) {
  const terms = researchTerms(queries);
  return sources
    .map((source) => {
      const quality = sourceQuality(source, terms, allowedDomains);
      return {
        ...source,
        research_quality_score: quality.score,
        research_term_matches: quality.termMatches,
        allowed_domain_match: quality.allowedDomainMatch,
      };
    })
    .filter(
      (source) =>
        source.research_term_matches > 0 || source.allowed_domain_match,
    )
    .sort(
      (left, right) =>
        right.research_quality_score - left.research_quality_score ||
        left.url.localeCompare(right.url),
    );
}

async function research(service, args, options) {
  const queries = uniqueStrings(args.queries, 6, 400);
  if (!queries.length)
    throw Object.assign(new Error("queries must contain 1-6 search queries"), {
      status: 400,
      code: "alta_web_invalid_queries",
    });
  const perQuery = boundedInteger(args.max_results_per_query, 8, 2, 12);
  const backend = args.backend ?? "federated";
  const allowedDomains = uniqueStrings(args.allowed_domains, 5, 253);
  const excludedDomains = uniqueStrings(args.excluded_domains, 5, 253);
  if (allowedDomains.length && excludedDomains.length)
    throw Object.assign(
      new Error("allowed_domains and excluded_domains cannot be combined"),
      { status: 400, code: "alta_web_domain_filters" },
    );
  const settled = await Promise.allSettled(
    queries.map((query) =>
      service.search(
        {
          query,
          depth: "deep",
          max_results: perQuery,
          backend,
          ...(allowedDomains.length ? { allowed_domains: allowedDomains } : {}),
          ...(excludedDomains.length
            ? { excluded_domains: excludedDomains }
            : {}),
          ...(args.freshness ? { freshness: args.freshness } : {}),
          ...(args.language ? { language: args.language } : {}),
        },
        options,
      ),
    ),
  );
  const searches = [];
  const failures = [];
  const sourceMap = new Map();
  settled.forEach((item, index) => {
    if (item.status === "rejected") {
      failures.push({
        query: queries[index],
        error: errorMessage(item.reason),
      });
      return;
    }
    const search = compactSearch(queries[index], item.value);
    searches.push(search);
    for (const result of search.results) {
      try {
        const url = new URL(result.url);
        url.hash = "";
        const existing = sourceMap.get(url.href);
        if (existing) {
          existing.queries.push(queries[index]);
          existing.backends = [
            ...new Set([
              ...(existing.backends ?? []),
              ...(result.backends ?? []),
            ]),
          ];
        } else {
          sourceMap.set(url.href, {
            ...result,
            url: url.href,
            queries: [queries[index]],
          });
        }
      } catch {}
    }
  });

  // A provider outage must not erase a precise issuer/regulator route. When
  // the caller supplied an allow-list and every engine returned no admissible
  // result, retain one bounded root locator per exact domain for direct fetch.
  // The fetched page is still only a source record; it does not prove a claim.
  if (!sourceMap.size && allowedDomains.length) {
    for (const domain of allowedDomains) {
      try {
        const url = new URL(`https://${domain}/`);
        if (!domainMatches(url.hostname, domain)) continue;
        sourceMap.set(url.href, {
          url: url.href,
          title: `Direct allowed-domain fallback for ${domain}`,
          snippets: [],
          backends: ["direct_domain"],
          queries: [...queries],
        });
      } catch {}
    }
  }

  const maxPages =
    args.fetch_pages === false ? 0 : boundedInteger(args.max_pages, 6, 0, 8);
  const maxChars = boundedInteger(args.max_chars, 30_000, 4_000, 32_000);
  const sourceList = rankSources(
    [...sourceMap.values()],
    queries,
    allowedDomains,
  ).slice(0, 30);
  const pageSettled = await Promise.allSettled(
    sourceList.slice(0, maxPages).map((source) =>
      service.fetchPage(
        {
          url: source.url,
          max_chars: Math.max(
            1_000,
            Math.floor(maxChars / Math.max(maxPages, 1)),
          ),
          reader: "auto",
        },
        options,
      ),
    ),
  );
  const pages = [];
  const completedPages = pageSettled.filter(
    (item) => item.status === "fulfilled",
  ).length;
  const pageTextBudget = Math.max(
    1_200,
    Math.floor(9_000 / Math.max(completedPages, 1)),
  );
  pageSettled.forEach((item, index) => {
    if (item.status === "fulfilled") {
      pages.push({
        url: item.value.url,
        title: item.value.title,
        text: String(item.value.text ?? "").slice(0, pageTextBudget),
        metadata: item.value.metadata,
        reader_used: item.value.reader_used,
      });
    } else {
      failures.push({
        url: sourceList[index].url,
        error: errorMessage(item.reason),
      });
    }
  });
  return {
    queries,
    // Keep fetched primary-source text ahead of discovery metadata. The MCP
    // boundary is byte-bounded, so placing pages last made a valid research
    // pack look empty whenever verbose search metadata consumed the preview.
    pages,
    sources: sourceList,
    searches,
    failures,
    partial: failures.length > 0,
  };
}

async function batchFetch(service, args, options) {
  const urls = uniqueStrings(args.urls, 8, 4_000);
  if (!urls.length)
    throw Object.assign(new Error("urls must contain 1-8 public URLs"), {
      status: 400,
      code: "alta_web_invalid_urls",
    });
  const perPage = boundedInteger(args.max_chars_per_page, 8_000, 1_000, 16_000);
  const evidenceWindowPerPage = Math.min(
    perPage,
    Math.max(1_200, Math.floor(9_000 / urls.length)),
  );
  const settled = await Promise.allSettled(
    urls.map((url) =>
      service.fetchPage(
        {
          url,
          max_chars: evidenceWindowPerPage,
          reader: args.reader ?? "auto",
        },
        options,
      ),
    ),
  );
  return {
    pages: settled.map((item, index) =>
      item.status === "fulfilled"
        ? item.value
        : { url: urls[index], error: errorMessage(item.reason) },
    ),
    failures: settled.filter((item) => item.status === "rejected").length,
    evidence_window_chars_per_page: evidenceWindowPerPage,
  };
}

export const researchPlugin = {
  id: "alta-deep-research",
  tools: [
    defineTool(
      "alta_web_research",
      "ALTA Deep Web Research",
      "Run up to six complementary searches, federate engines, deduplicate sources, and optionally fetch the strongest pages into one bounded evidence pack.",
      {
        type: "object",
        properties: {
          queries: {
            type: "array",
            minItems: 1,
            maxItems: 6,
            items: { type: "string" },
          },
          backend: { type: "string", default: "federated" },
          allowed_domains: {
            type: "array",
            maxItems: 5,
            items: { type: "string" },
          },
          excluded_domains: {
            type: "array",
            maxItems: 5,
            items: { type: "string" },
          },
          freshness: {
            type: "string",
            description:
              "Backend-supported recency window such as day/month/year.",
          },
          language: {
            type: "string",
            description: "Preferred search language code.",
          },
          max_results_per_query: { type: "integer", minimum: 2, maximum: 12 },
          fetch_pages: { type: "boolean", default: true },
          max_pages: { type: "integer", minimum: 0, maximum: 8 },
          max_chars: { type: "integer", minimum: 4_000, maximum: 32_000 },
        },
        required: ["queries"],
        additionalProperties: false,
      },
      research,
    ),
    defineTool(
      "alta_web_batch_fetch",
      "ALTA Batch Web Fetch",
      "Fetch up to eight independent public URLs concurrently with partial-failure handling and bounded output.",
      {
        type: "object",
        properties: {
          urls: {
            type: "array",
            minItems: 1,
            maxItems: 8,
            items: { type: "string" },
          },
          max_chars_per_page: {
            type: "integer",
            minimum: 1_000,
            maximum: 16_000,
          },
          reader: { type: "string", enum: ["auto", "direct", "reader"] },
        },
        required: ["urls"],
        additionalProperties: false,
      },
      batchFetch,
    ),
  ],
};
