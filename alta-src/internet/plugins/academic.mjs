import { parseFeed } from "./discovery.mjs";
import { boundedInteger, defineTool, uniqueStrings } from "./support.mjs";
import { settleSources } from "./source-runtime.mjs";

const SOURCES = new Set(["openalex", "crossref", "arxiv"]);

function year(value, name) {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1000 || parsed > 2100)
    throw Object.assign(new Error(`${name} must be a year from 1000-2100`), {
      status: 400,
      code: "alta_academic_invalid_year",
    });
  return parsed;
}

function cleanMarkup(value, maximum = 1_500) {
  return String(value ?? "")
    .replace(/<[^>]*>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maximum);
}

function dateParts(value) {
  const parts = value?.["date-parts"]?.[0];
  if (!Array.isArray(parts) || !parts.length) return "";
  return parts
    .map((part, index) => String(part).padStart(index ? 2 : 4, "0"))
    .join("-");
}

function openAlexAbstract(index) {
  if (!index || typeof index !== "object") return "";
  const positioned = [];
  words: for (const [word, positions] of Object.entries(index)) {
    if (!Array.isArray(positions)) continue;
    for (const position of positions.slice(0, 100)) {
      if (Number.isInteger(position) && position >= 0 && position < 5_000) {
        positioned.push([position, word]);
        if (positioned.length >= 5_000) break words;
      }
    }
  }
  return positioned
    .sort(([left], [right]) => left - right)
    .map(([, word]) => word)
    .join(" ")
    .slice(0, 1_500);
}

async function openAlex(service, query, maximum, range, options) {
  const url = new URL("https://api.openalex.org/works");
  url.searchParams.set("search", query);
  url.searchParams.set("per-page", String(maximum));
  if (service.openAlexKey) url.searchParams.set("api_key", service.openAlexKey);
  const filters = [];
  if (range.from) filters.push(`from_publication_date:${range.from}-01-01`);
  if (range.to) filters.push(`to_publication_date:${range.to}-12-31`);
  if (filters.length) url.searchParams.set("filter", filters.join(","));
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/json",
      max_chars: 1_000_000,
      cache_namespace: "academic-openalex",
    },
    options,
  );
  return (JSON.parse(response.text).results ?? []).map((item) => ({
    title: cleanMarkup(item.display_name, 500),
    url:
      item.best_oa_location?.landing_page_url ??
      item.primary_location?.landing_page_url ??
      item.doi ??
      item.id,
    pdf_url: item.best_oa_location?.pdf_url ?? "",
    doi: String(item.doi ?? "").replace(/^https?:\/\/doi\.org\//i, ""),
    authors: (item.authorships ?? [])
      .map((entry) => entry.author?.display_name)
      .filter(Boolean)
      .slice(0, 20),
    publication_date: item.publication_date ?? "",
    venue: item.primary_location?.source?.display_name ?? "",
    type: item.type ?? "",
    abstract: openAlexAbstract(item.abstract_inverted_index),
    cited_by_count: item.cited_by_count ?? 0,
    open_access: item.open_access?.is_oa ?? false,
    source: "openalex",
    source_id: item.id,
  }));
}

async function crossref(service, query, maximum, range, options) {
  const url = new URL("https://api.crossref.org/works");
  url.searchParams.set("query.bibliographic", query);
  url.searchParams.set("rows", String(maximum));
  if (service.crossrefMailto)
    url.searchParams.set("mailto", service.crossrefMailto);
  const filters = [];
  if (range.from) filters.push(`from-pub-date:${range.from}-01-01`);
  if (range.to) filters.push(`until-pub-date:${range.to}-12-31`);
  if (filters.length) url.searchParams.set("filter", filters.join(","));
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/json",
      max_chars: 1_000_000,
      cache_namespace: "academic-crossref",
    },
    options,
  );
  return (JSON.parse(response.text).message?.items ?? []).map((item) => ({
    title: cleanMarkup(item.title?.[0], 500),
    url: item.URL ?? (item.DOI ? `https://doi.org/${item.DOI}` : ""),
    pdf_url:
      item.link?.find((link) => /pdf/i.test(link["content-type"]))?.URL ?? "",
    doi: item.DOI ?? "",
    authors: (item.author ?? [])
      .map((author) => [author.given, author.family].filter(Boolean).join(" "))
      .filter(Boolean)
      .slice(0, 20),
    publication_date:
      dateParts(item.published) ||
      dateParts(item["published-online"]) ||
      dateParts(item["published-print"]),
    venue: item["container-title"]?.[0] ?? item.publisher ?? "",
    type: item.type ?? "",
    abstract: cleanMarkup(item.abstract),
    cited_by_count: item["is-referenced-by-count"] ?? 0,
    open_access: Boolean(item.license?.length),
    source: "crossref",
    source_id: item.DOI ?? item.URL,
  }));
}

async function arxiv(service, query, maximum, range, options) {
  const url = new URL("https://export.arxiv.org/api/query");
  url.searchParams.set("search_query", `all:${query}`);
  url.searchParams.set("start", "0");
  url.searchParams.set("max_results", String(maximum));
  url.searchParams.set("sortBy", "relevance");
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/atom+xml",
      max_chars: 1_000_000,
      cache_namespace: "academic-arxiv",
    },
    options,
  );
  return parseFeed(response.text, response.url, maximum)
    .filter((item) => {
      const publishedYear = Number(String(item.published).slice(0, 4));
      return (
        (!range.from || publishedYear >= range.from) &&
        (!range.to || publishedYear <= range.to)
      );
    })
    .map((item) => ({
      title: item.title,
      url: item.url,
      pdf_url: item.url?.replace("/abs/", "/pdf/") ?? "",
      doi: "",
      authors: item.author ? [item.author] : [],
      publication_date: item.published,
      venue: "arXiv",
      type: "preprint",
      abstract: item.summary,
      cited_by_count: null,
      open_access: true,
      source: "arxiv",
      source_id: item.url,
    }));
}

const SEARCHERS = { openalex: openAlex, crossref, arxiv };

function identity(item) {
  if (item.doi) return `doi:${item.doi.toLowerCase()}`;
  return `title:${item.title
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim()}`;
}

function mergeResults(values, maximum) {
  const merged = new Map();
  for (let index = 0; merged.size < maximum; index += 1) {
    let found = false;
    for (const { source, results } of values) {
      const item = results[index];
      if (!item) continue;
      found = true;
      const key = identity(item);
      const previous = merged.get(key);
      if (!previous) {
        merged.set(key, { ...item, sources: [source] });
      } else {
        previous.sources.push(source);
        for (const field of ["abstract", "doi", "pdf_url", "venue"])
          if (!previous[field] && item[field]) previous[field] = item[field];
        previous.cited_by_count = Math.max(
          previous.cited_by_count ?? 0,
          item.cited_by_count ?? 0,
        );
      }
      if (merged.size >= maximum) break;
    }
    if (!found) break;
  }
  return [...merged.values()];
}

async function academicSearch(service, args, options) {
  const query = String(args.query ?? "").trim();
  if (!query || query.length > 400)
    throw Object.assign(new Error("query must contain 1-400 characters"), {
      status: 400,
      code: "alta_academic_invalid_query",
    });
  const maximum = boundedInteger(args.max_results, 12, 1, 20);
  const requested = uniqueStrings(args.sources, 3, 20);
  const sources = requested.length ? requested : [...SOURCES];
  if (sources.some((source) => !SOURCES.has(source)))
    throw Object.assign(new Error("Unsupported academic source"), {
      status: 400,
      code: "alta_academic_invalid_source",
    });
  const range = {
    from: year(args.from_year, "from_year"),
    to: year(args.to_year, "to_year"),
  };
  if (range.from && range.to && range.from > range.to)
    throw Object.assign(new Error("from_year must not exceed to_year"), {
      status: 400,
      code: "alta_academic_invalid_range",
    });
  const settled = await settleSources(
    service,
    "academic",
    sources,
    options,
    (source, sourceOptions) =>
      SEARCHERS[source](service, query, maximum, range, sourceOptions),
    {
      intervals: { arxiv: 3_000 },
      deadlines: { openalex: 12_000, crossref: 12_000, arxiv: 15_000 },
    },
  );
  const values = settled.values.map(({ source, value }) => ({
    source,
    results: value.filter((item) => item.title && item.url),
  }));
  const { failures } = settled;
  if (!values.length)
    throw Object.assign(new Error("All academic sources failed"), {
      status: 503,
      code: "alta_academic_unavailable",
    });
  const results = mergeResults(values, maximum);
  return {
    query,
    sources: values.map(({ source }) => source),
    results,
    result_count: results.length,
    failures,
    partial: failures.length > 0,
  };
}

export const academicPlugin = {
  id: "alta-scholarly-discovery",
  tools: [
    defineTool(
      "alta_academic_search",
      "ALTA Academic Search",
      "Federate OpenAlex, Crossref, and arXiv for scholarly works, DOI metadata, preprints, citations, and open-access links with bounded partial-failure handling.",
      {
        type: "object",
        properties: {
          query: { type: "string" },
          sources: {
            type: "array",
            maxItems: 3,
            items: {
              type: "string",
              enum: ["openalex", "crossref", "arxiv"],
            },
          },
          max_results: { type: "integer", minimum: 1, maximum: 20 },
          from_year: { type: "integer", minimum: 1000, maximum: 2100 },
          to_year: { type: "integer", minimum: 1000, maximum: 2100 },
        },
        required: ["query"],
        additionalProperties: false,
      },
      academicSearch,
    ),
  ],
};
