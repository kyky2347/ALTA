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

async function research(service, args, options) {
  const queries = uniqueStrings(args.queries, 6, 400);
  if (!queries.length)
    throw Object.assign(new Error("queries must contain 1-6 search queries"), {
      status: 400,
      code: "alta_web_invalid_queries",
    });
  const perQuery = boundedInteger(args.max_results_per_query, 8, 2, 12);
  const backend = args.backend ?? "federated";
  const settled = await Promise.allSettled(
    queries.map((query) =>
      service.search(
        { query, depth: "deep", max_results: perQuery, backend },
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

  const maxPages =
    args.fetch_pages === false ? 0 : boundedInteger(args.max_pages, 6, 0, 8);
  const maxChars = boundedInteger(args.max_chars, 30_000, 4_000, 32_000);
  const sourceList = [...sourceMap.values()].slice(0, 30);
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
  pageSettled.forEach((item, index) => {
    if (item.status === "fulfilled") {
      pages.push({
        url: item.value.url,
        title: item.value.title,
        text: item.value.text,
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
    searches,
    sources: sourceList,
    pages,
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
  const settled = await Promise.allSettled(
    urls.map((url) =>
      service.fetchPage(
        { url, max_chars: perPage, reader: args.reader ?? "auto" },
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
