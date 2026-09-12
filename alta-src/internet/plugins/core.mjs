import { defineTool } from "./support.mjs";

const SEARCH_SCHEMA = {
  type: "object",
  properties: {
    query: {
      type: "string",
      description:
        "Search query, including normal search operators when useful.",
    },
    depth: {
      type: "string",
      enum: ["quick", "deep"],
      description: "Use deep for difficult multi-source investigation.",
    },
    max_results: { type: "integer", minimum: 1, maximum: 20 },
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
      description: "day/week/month/year or YYYY-MM-DDtoYYYY-MM-DD",
    },
    language: { type: "string" },
    backend: {
      type: "string",
      enum: [
        "auto",
        "federated",
        "brave",
        "xai",
        "jina",
        "searxng",
        "public",
        "duckduckgo",
        "bing",
      ],
    },
  },
  required: ["query"],
  additionalProperties: false,
};

export const corePlugin = {
  id: "alta-core-web",
  tools: [
    defineTool(
      "alta_web_search",
      "ALTA Web Search",
      "Search the public internet with provider failover or federated retrieval. Choose only advertised engines; corroborate results with source documents.",
      SEARCH_SCHEMA,
      (service, args, options) => service.search(args, options),
    ),
    defineTool(
      "alta_web_fetch",
      "ALTA Web Fetch",
      "Fetch and extract a public page. For long filings use focus (a literal phrase, such as revenue) and/or offset to retrieve the relevant excerpt instead of boilerplate. Returned offsets refer to extracted text, not HTML. Auto mode can use Jina Reader for PDFs or blocked direct fetches.",
      {
        type: "object",
        properties: {
          url: { type: "string" },
          max_chars: { type: "integer", minimum: 1_000, maximum: 40_000 },
          reader: { type: "string", enum: ["auto", "direct", "reader"] },
          focus: { type: "string", maxLength: 200 },
          offset: { type: "integer", minimum: 0, maximum: 4_000_000 },
        },
        required: ["url"],
        additionalProperties: false,
      },
      (service, args, options) => service.fetchPage(args, options),
    ),
    defineTool(
      "alta_web_crawl",
      "ALTA Web Crawl",
      "Crawl bounded same-origin pages. Optional query prioritizes retrieved links by matching URL/anchor text, e.g. investor earnings filings, instead of menu order. Link priority is not evidence.",
      {
        type: "object",
        properties: {
          url: { type: "string" },
          max_pages: { type: "integer", minimum: 1, maximum: 12 },
          max_depth: { type: "integer", minimum: 0, maximum: 2 },
          max_chars: { type: "integer", minimum: 2_000, maximum: 40_000 },
          query: { type: "string", maxLength: 400 },
        },
        required: ["url"],
        additionalProperties: false,
      },
      (service, args, options) => service.crawl(args, options),
    ),
  ],
};
