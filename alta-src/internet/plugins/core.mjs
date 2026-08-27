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
    freshness: { type: "string" },
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
      "Search the live public internet with automatic provider failover or federated multi-engine retrieval. Every ALTA agent can call this independently at any depth.",
      SEARCH_SCHEMA,
      (service, args, options) => service.search(args, options),
    ),
    defineTool(
      "alta_web_fetch",
      "ALTA Web Fetch",
      "Fetch and extract a public page. Auto mode can use the bundled Jina Reader adapter for JavaScript-heavy pages, PDFs, or blocked direct fetches.",
      {
        type: "object",
        properties: {
          url: { type: "string" },
          max_chars: { type: "integer", minimum: 1_000, maximum: 40_000 },
          reader: { type: "string", enum: ["auto", "direct", "reader"] },
        },
        required: ["url"],
        additionalProperties: false,
      },
      (service, args, options) => service.fetchPage(args, options),
    ),
    defineTool(
      "alta_web_crawl",
      "ALTA Web Crawl",
      "Crawl a hard-bounded set of same-origin public pages for documentation or site research.",
      {
        type: "object",
        properties: {
          url: { type: "string" },
          max_pages: { type: "integer", minimum: 1, maximum: 12 },
          max_depth: { type: "integer", minimum: 0, maximum: 2 },
          max_chars: { type: "integer", minimum: 2_000, maximum: 40_000 },
        },
        required: ["url"],
        additionalProperties: false,
      },
      (service, args, options) => service.crawl(args, options),
    ),
  ],
};
