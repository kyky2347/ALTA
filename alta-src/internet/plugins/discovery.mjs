import { assertPublicUrl } from "../content.mjs";
import {
  boundedInteger,
  defineTool,
  errorMessage,
  uniqueStrings,
} from "./support.mjs";

function decodeXml(value) {
  return String(value ?? "")
    .replace(/<!\[CDATA\[([\s\S]*?)]]>/g, "$1")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .trim();
}

function tagValue(block, tag) {
  return decodeXml(
    block.match(
      new RegExp(`<${tag}\\b[^>]*>([\\s\\S]*?)<\\/${tag}>`, "i"),
    )?.[1],
  );
}

function stripMarkup(value) {
  return decodeXml(String(value ?? "").replace(/<[^>]*>/g, " "))
    .replace(/\s+/g, " ")
    .trim();
}

function publicUrl(value, baseUrl) {
  try {
    const url = new URL(decodeXml(value), baseUrl);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

export function parseSitemapXml(xml, baseUrl) {
  const locations = [];
  for (const match of xml.matchAll(/<loc\b[^>]*>([\s\S]*?)<\/loc>/gi)) {
    const url = publicUrl(match[1], baseUrl);
    if (url) locations.push(url);
  }
  return {
    kind: /<sitemapindex\b/i.test(xml) ? "index" : "urlset",
    locations: [...new Set(locations)],
  };
}

export function parseFeed(text, baseUrl, maximum = 20) {
  try {
    const value = JSON.parse(text);
    if (Array.isArray(value.items)) {
      return value.items.slice(0, maximum).map((item) => ({
        title: String(item.title ?? "").slice(0, 500),
        url: publicUrl(item.url ?? item.external_url ?? item.id, baseUrl),
        published: item.date_published ?? item.date_modified ?? "",
        author: item.author?.name ?? item.authors?.[0]?.name ?? "",
        summary: stripMarkup(
          item.summary ?? item.content_text ?? item.content_html,
        ).slice(0, 1_500),
      }));
    }
  } catch {}
  const atom = /<feed\b/i.test(text);
  const blocks = atom
    ? [...text.matchAll(/<entry\b[^>]*>([\s\S]*?)<\/entry>/gi)]
    : [...text.matchAll(/<item\b[^>]*>([\s\S]*?)<\/item>/gi)];
  return blocks.slice(0, maximum).map((match) => {
    const block = match[1];
    const linkTag = block.match(/<link\b[^>]*>/i)?.[0] ?? "";
    const atomHref = linkTag.match(/\bhref\s*=\s*["']([^"']+)["']/i)?.[1];
    return {
      title: stripMarkup(tagValue(block, "title")).slice(0, 500),
      url: publicUrl(
        atomHref || tagValue(block, "link") || tagValue(block, "guid"),
        baseUrl,
      ),
      published:
        tagValue(block, "published") ||
        tagValue(block, "updated") ||
        tagValue(block, "pubDate"),
      author: stripMarkup(
        tagValue(block, "author") || tagValue(block, "dc:creator"),
      ),
      summary: stripMarkup(
        tagValue(block, "summary") ||
          tagValue(block, "description") ||
          tagValue(block, "content"),
      ).slice(0, 1_500),
    };
  });
}

async function discoverSitemap(service, args, options) {
  const maximum = boundedInteger(args.max_urls, 100, 1, 200);
  const start = await assertPublicUrl(args.url, {
    lookup: service.lookup,
    allowProxyFakeIp: service.settings.allowProxyFakeIp,
  });
  const candidates = [];
  if (/\.(?:xml|xml\.gz)$/i.test(start.pathname)) candidates.push(start.href);
  const robotsUrl = new URL("/robots.txt", start.origin).href;
  try {
    const robots = await service.readText(
      { url: robotsUrl, max_chars: 64_000, cache_namespace: "robots" },
      options,
    );
    for (const match of robots.text.matchAll(/^\s*Sitemap:\s*(\S+)/gim)) {
      const url = publicUrl(match[1], robotsUrl);
      if (url) candidates.push(url);
    }
  } catch {}
  candidates.push(new URL("/sitemap.xml", start.origin).href);

  const queue = uniqueStrings(candidates, 8, 4_000);
  const visited = new Set();
  const urls = [];
  const failures = [];
  while (queue.length && visited.size < 8 && urls.length < maximum) {
    const sitemapUrl = queue.shift();
    if (visited.has(sitemapUrl)) continue;
    visited.add(sitemapUrl);
    try {
      const response = await service.readText(
        {
          url: sitemapUrl,
          accept: "application/xml,text/xml,text/plain",
          max_chars: 512_000,
          cache_namespace: "sitemap",
        },
        options,
      );
      const parsed = parseSitemapXml(response.text, response.url);
      if (parsed.kind === "index") {
        for (const nested of parsed.locations)
          if (!visited.has(nested) && queue.length < 16) queue.push(nested);
      } else {
        for (const url of parsed.locations) {
          if (!urls.includes(url)) urls.push(url);
          if (urls.length >= maximum) break;
        }
      }
    } catch (error) {
      failures.push({ url: sitemapUrl, error: errorMessage(error) });
    }
  }
  return {
    site: start.origin,
    sitemaps: [...visited],
    urls,
    url_count: urls.length,
    failures,
    truncated: queue.length > 0 || urls.length >= maximum,
  };
}

async function readFeed(service, args, options) {
  const maximum = boundedInteger(args.max_items, 20, 1, 50);
  let url = args.url;
  if (args.discover === true) {
    const page = await service.fetchPage(
      { url, max_chars: 4_000, reader: "direct" },
      options,
    );
    url = page.metadata?.feeds?.[0]?.url ?? url;
  }
  const response = await service.readText(
    {
      url,
      accept:
        "application/feed+json,application/atom+xml,application/rss+xml,application/xml,text/xml",
      max_chars: 512_000,
      cache_namespace: "feed",
    },
    options,
  );
  const items = parseFeed(response.text, response.url, maximum);
  return {
    url: response.url,
    items,
    item_count: items.length,
    truncated: items.length >= maximum || response.truncated,
  };
}

function dateValue(value) {
  const text = String(value ?? "").trim();
  return /^\d{1,14}$/.test(text) ? text : "";
}

async function wayback(service, target, args, options) {
  const url = new URL("https://web.archive.org/cdx/search/cdx");
  url.searchParams.set("url", target.href);
  url.searchParams.set("output", "json");
  url.searchParams.set(
    "fl",
    "timestamp,original,statuscode,mimetype,digest,length",
  );
  url.searchParams.set("filter", "statuscode:200");
  url.searchParams.set("collapse", "digest");
  url.searchParams.set("limit", String(args.limit));
  if (args.match_type !== "exact")
    url.searchParams.set("matchType", args.match_type);
  if (args.from) url.searchParams.set("from", args.from);
  if (args.to) url.searchParams.set("to", args.to);
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/json",
      max_chars: 512_000,
      cache_namespace: "wayback",
    },
    options,
  );
  const rows = JSON.parse(response.text);
  const headers = rows[0] ?? [];
  return rows.slice(1).map((row) => {
    const item = Object.fromEntries(
      headers.map((name, index) => [name, row[index]]),
    );
    return {
      ...item,
      snapshot_url: `https://web.archive.org/web/${item.timestamp}/${item.original}`,
    };
  });
}

async function commonCrawl(service, target, args, options) {
  const catalogs = await service.readText(
    {
      url: "https://index.commoncrawl.org/collinfo.json",
      accept: "application/json",
      max_chars: 256_000,
      cache_namespace: "commoncrawl-catalog",
    },
    options,
  );
  const latest = JSON.parse(catalogs.text)?.[0];
  const endpoint = latest?.["cdx-api"];
  if (!endpoint)
    throw new Error("Common Crawl did not publish an index endpoint");
  const url = new URL(endpoint);
  url.searchParams.set("url", target.href);
  url.searchParams.set("output", "json");
  url.searchParams.set("filter", "status:200");
  url.searchParams.set("limit", String(args.limit));
  if (args.match_type !== "exact")
    url.searchParams.set("matchType", args.match_type);
  if (args.from) url.searchParams.set("from", args.from);
  if (args.to) url.searchParams.set("to", args.to);
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/x-ndjson,text/plain",
      max_chars: 512_000,
      cache_namespace: "commoncrawl-index",
    },
    options,
  );
  return response.text
    .split("\n")
    .filter(Boolean)
    .slice(0, args.limit)
    .map((line) => JSON.parse(line))
    .map((item) => ({
      timestamp: item.timestamp,
      original: item.url,
      statuscode: item.status,
      mimetype: item.mime,
      digest: item.digest,
      length: item.length,
      crawl: latest.id,
      warc_url: item.filename
        ? `https://data.commoncrawl.org/${item.filename}`
        : null,
      warc_offset: item.offset,
    }));
}

async function archiveLookup(service, args, options) {
  const target = await assertPublicUrl(args.url, {
    lookup: service.lookup,
    allowProxyFakeIp: service.settings.allowProxyFakeIp,
  });
  const normalized = {
    limit: boundedInteger(args.limit, 20, 1, 50),
    match_type: ["exact", "prefix", "host", "domain"].includes(args.match_type)
      ? args.match_type
      : "exact",
    from: dateValue(args.from),
    to: dateValue(args.to),
  };
  const provider = args.provider ?? "auto";
  if (provider === "wayback")
    return {
      provider,
      captures: await wayback(service, target, normalized, options),
    };
  if (provider === "commoncrawl")
    return {
      provider,
      captures: await commonCrawl(service, target, normalized, options),
    };
  const failures = [];
  try {
    const captures = await wayback(service, target, normalized, options);
    if (captures.length) return { provider: "wayback", captures, failures };
  } catch (error) {
    failures.push({ provider: "wayback", error: errorMessage(error) });
  }
  const captures = await commonCrawl(service, target, normalized, options);
  return { provider: "commoncrawl", captures, failures };
}

export const discoveryPlugin = {
  id: "alta-open-web-discovery",
  tools: [
    defineTool(
      "alta_web_sitemap",
      "ALTA Sitemap Discovery",
      "Discover robots-declared and conventional sitemaps, follow bounded sitemap indexes, and return a deduplicated URL inventory.",
      {
        type: "object",
        properties: {
          url: { type: "string" },
          max_urls: { type: "integer", minimum: 1, maximum: 200 },
        },
        required: ["url"],
        additionalProperties: false,
      },
      discoverSitemap,
    ),
    defineTool(
      "alta_web_feed",
      "ALTA Feed Reader",
      "Read RSS, Atom, or JSON Feed data; optionally discover the feed URL from a web page first.",
      {
        type: "object",
        properties: {
          url: { type: "string" },
          discover: { type: "boolean", default: false },
          max_items: { type: "integer", minimum: 1, maximum: 50 },
        },
        required: ["url"],
        additionalProperties: false,
      },
      readFeed,
    ),
    defineTool(
      "alta_web_archive",
      "ALTA Web Archive Lookup",
      "Find bounded historical captures through Internet Archive Wayback CDX with automatic Common Crawl index fallback.",
      {
        type: "object",
        properties: {
          url: { type: "string" },
          provider: {
            type: "string",
            enum: ["auto", "wayback", "commoncrawl"],
          },
          match_type: {
            type: "string",
            enum: ["exact", "prefix", "host", "domain"],
          },
          from: {
            type: "string",
            description: "1-14 digit UTC timestamp prefix.",
          },
          to: {
            type: "string",
            description: "1-14 digit UTC timestamp prefix.",
          },
          limit: { type: "integer", minimum: 1, maximum: 50 },
        },
        required: ["url"],
        additionalProperties: false,
      },
      archiveLookup,
    ),
  ],
};
