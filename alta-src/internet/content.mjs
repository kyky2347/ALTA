import dns from "node:dns/promises";
import net from "node:net";

const DISPLAY_ONLY_HOSTS = ["tradingview.com"];
const DISALLOWED_REPOSITORY_HOSTS = [
  "github.com",
  "githubassets.com",
  "githubusercontent.com",
];

function normalizedHostname(url) {
  return url.hostname
    .replace(/^\[|\]$/g, "")
    .replace(/\.+$/, "")
    .toLowerCase();
}

export function assertAutomatedSitePolicy(url) {
  const hostname = normalizedHostname(url);
  if (
    DISALLOWED_REPOSITORY_HOSTS.some(
      (blocked) => hostname === blocked || hostname.endsWith(`.${blocked}`),
    )
  ) {
    throw Object.assign(
      new Error(
        "Repository-host access is outside ALTA's research-tool policy",
      ),
      { status: 403, code: "alta_web_repository_host_disabled" },
    );
  }
  if (
    DISPLAY_ONLY_HOSTS.some(
      (blocked) => hostname === blocked || hostname.endsWith(`.${blocked}`),
    )
  ) {
    throw Object.assign(
      new Error(
        "TradingView permits display-only access; use alta_tradingview_navigate and open the returned page manually",
      ),
      { status: 403, code: "alta_web_site_policy" },
    );
  }
}

const PRIVATE_IPV4 = [
  ["0.0.0.0", 8],
  ["10.0.0.0", 8],
  ["100.64.0.0", 10],
  ["127.0.0.0", 8],
  ["169.254.0.0", 16],
  ["172.16.0.0", 12],
  ["192.0.0.0", 24],
  ["192.0.2.0", 24],
  ["192.168.0.0", 16],
  ["198.51.100.0", 24],
  ["203.0.113.0", 24],
  ["224.0.0.0", 4],
];

function ipv4Number(address) {
  return (
    address
      .split(".")
      .reduce((value, part) => (value << 8) + Number(part), 0) >>> 0
  );
}

function ipv4InCidr(address, network, bits) {
  const mask = bits === 0 ? 0 : (0xffffffff << (32 - bits)) >>> 0;
  return (ipv4Number(address) & mask) === (ipv4Number(network) & mask);
}

export function isPublicAddress(address, { allowProxyFakeIp = false } = {}) {
  if (net.isIPv4(address)) {
    if (allowProxyFakeIp && ipv4InCidr(address, "198.18.0.0", 15)) return true;
    if (ipv4InCidr(address, "198.18.0.0", 15)) return false;
    return !PRIVATE_IPV4.some(([network, bits]) =>
      ipv4InCidr(address, network, bits),
    );
  }
  if (!net.isIPv6(address)) return false;
  const normalized = address.toLowerCase().split("%")[0];
  if (
    normalized === "::" ||
    normalized === "::1" ||
    normalized.startsWith("fc") ||
    normalized.startsWith("fd") ||
    /^(fe[89ab])/i.test(normalized) ||
    normalized.startsWith("2001:db8:")
  ) {
    return false;
  }
  const mapped = normalized.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/);
  return mapped ? isPublicAddress(mapped[1], { allowProxyFakeIp }) : true;
}

export async function assertPublicUrl(
  value,
  { lookup = dns.lookup, allowProxyFakeIp = false } = {},
) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw Object.assign(new Error("URL is not valid"), {
      status: 400,
      code: "alta_web_invalid_url",
    });
  }
  if (!["http:", "https:"].includes(url.protocol)) {
    throw Object.assign(new Error("Only public HTTP(S) URLs are supported"), {
      status: 400,
      code: "alta_web_invalid_scheme",
    });
  }
  if (url.username || url.password) {
    throw Object.assign(new Error("URLs cannot contain credentials"), {
      status: 400,
      code: "alta_web_url_credentials",
    });
  }
  assertAutomatedSitePolicy(url);
  const hostname = normalizedHostname(url);
  const addresses = net.isIP(hostname)
    ? [{ address: hostname }]
    : await lookup(hostname, { all: true, verbatim: true });
  if (
    !addresses.length ||
    addresses.some(
      ({ address }) => !isPublicAddress(address, { allowProxyFakeIp }),
    )
  ) {
    throw Object.assign(
      new Error(
        "Private, local, reserved, or unresolvable network targets are blocked",
      ),
      { status: 403, code: "alta_web_private_target" },
    );
  }
  return url;
}

function decodeEntities(value) {
  const named = {
    amp: "&",
    apos: "'",
    gt: ">",
    hellip: "…",
    laquo: "«",
    ldquo: "“",
    lt: "<",
    nbsp: " ",
    quot: '"',
    raquo: "»",
    rdquo: "”",
  };
  return value.replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, (match, entity) => {
    if (entity[0] === "#") {
      const radix = entity[1]?.toLowerCase() === "x" ? 16 : 10;
      const digits = radix === 16 ? entity.slice(2) : entity.slice(1);
      const point = Number.parseInt(digits, radix);
      return Number.isFinite(point) && point <= 0x10ffff
        ? String.fromCodePoint(point)
        : match;
    }
    return named[entity.toLowerCase()] ?? match;
  });
}

function cleanWhitespace(value) {
  return value
    .replace(/\r/g, "")
    .replace(/[\t\f\v ]+/g, " ")
    .replace(/ *\n */g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function stripTags(value) {
  return cleanWhitespace(decodeEntities(value.replace(/<[^>]*>/g, " ")));
}

function absoluteLink(value, baseUrl) {
  try {
    const url = new URL(decodeEntities(value), baseUrl);
    if (!["http:", "https:"].includes(url.protocol)) return null;
    url.hash = "";
    return url.href;
  } catch {
    return null;
  }
}

function attribute(tag, name) {
  const match = tag.match(
    new RegExp(`\\b${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)'|([^\\s>]+))`, "i"),
  );
  return decodeEntities(match?.[1] ?? match?.[2] ?? match?.[3] ?? "");
}

function htmlMetadata(html, baseUrl) {
  const metadata = {
    description: "",
    author: "",
    published_time: "",
    canonical_url: "",
    language: attribute(html.match(/<html\b[^>]*>/i)?.[0] ?? "", "lang"),
    feeds: [],
    structured_data: [],
  };
  for (const match of html.matchAll(/<meta\b[^>]*>/gi)) {
    const tag = match[0];
    const name = (
      attribute(tag, "name") || attribute(tag, "property")
    ).toLowerCase();
    const content = cleanWhitespace(attribute(tag, "content"));
    if (!content) continue;
    if (["description", "og:description", "twitter:description"].includes(name))
      metadata.description ||= content;
    if (["author", "article:author"].includes(name))
      metadata.author ||= content;
    if (["article:published_time", "date", "datepublished"].includes(name))
      metadata.published_time ||= content;
  }
  for (const match of html.matchAll(/<link\b[^>]*>/gi)) {
    const tag = match[0];
    const rel = attribute(tag, "rel").toLowerCase().split(/\s+/);
    const href = absoluteLink(attribute(tag, "href"), baseUrl);
    if (!href) continue;
    if (rel.includes("canonical")) metadata.canonical_url ||= href;
    const type = attribute(tag, "type").toLowerCase();
    if (
      rel.includes("alternate") &&
      [
        "application/rss+xml",
        "application/atom+xml",
        "application/feed+json",
      ].includes(type)
    ) {
      metadata.feeds.push({ url: href, type });
    }
  }
  for (const match of html.matchAll(
    /<script\b[^>]*type\s*=\s*["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi,
  )) {
    if (metadata.structured_data.length >= 8) break;
    try {
      const value = JSON.parse(match[1]);
      metadata.structured_data.push(value);
    } catch {}
  }
  return metadata;
}

export function extractHtml(html, baseUrl, { maxLinks = 200 } = {}) {
  const title = stripTags(
    html.match(/<title\b[^>]*>([\s\S]*?)<\/title>/i)?.[1] ?? "",
  );
  const links = [];
  const seen = new Set();
  for (const match of html.matchAll(
    /<a\b[^>]*\bhref\s*=\s*(["'])(.*?)\1[^>]*>([\s\S]*?)<\/a>/gi,
  )) {
    const url = absoluteLink(match[2], baseUrl);
    if (!url || seen.has(url)) continue;
    seen.add(url);
    links.push({ url, text: stripTags(match[3]).slice(0, 240) });
    if (links.length >= maxLinks) break;
  }
  const text = cleanWhitespace(
    decodeEntities(
      html
        .replace(/<!--[\s\S]*?-->/g, " ")
        .replace(/<head\b[^>]*>[\s\S]*?<\/head>/gi, " ")
        .replace(
          /<(script|style|svg|canvas|template|noscript|nav|footer|header|aside)\b[^>]*>[\s\S]*?<\/\1>/gi,
          " ",
        )
        .replace(/<(br|hr)\b[^>]*>/gi, "\n")
        .replace(
          /<\/(p|div|section|article|main|li|tr|h[1-6]|blockquote|pre)>/gi,
          "\n",
        )
        .replace(/<li\b[^>]*>/gi, "- ")
        .replace(/<[^>]*>/g, " "),
    ),
  );
  return { title, text, links, metadata: htmlMetadata(html, baseUrl) };
}

export function extractDocument(body, contentType, url) {
  const type = String(contentType ?? "").toLowerCase();
  if (
    type.includes("text/html") ||
    /^\s*<!doctype html|^\s*<html/i.test(body)
  ) {
    return { kind: "html", ...extractHtml(body, url) };
  }
  if (
    type.includes("text/") ||
    type.includes("json") ||
    type.includes("xml") ||
    type.includes("javascript") ||
    !type
  ) {
    return {
      kind: type.includes("json") ? "json" : "text",
      title: "",
      text: cleanWhitespace(body),
      links: [],
      metadata: {},
    };
  }
  return {
    kind: "binary",
    title: "",
    text: `Binary content (${contentType || "unknown content type"}) is not expanded by ALTA.`,
    links: [],
    metadata: {},
  };
}
