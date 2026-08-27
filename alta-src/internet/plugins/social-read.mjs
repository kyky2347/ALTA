import { runSource } from "./source-runtime.mjs";
import { assertAutomatedSitePolicy } from "../content.mjs";
import { cleanSocial } from "./social-sources.mjs";
import { platformForUrl } from "./social-platforms.mjs";
import { boundedInteger } from "./support.mjs";

const OEMBED_ENDPOINTS = {
  reddit: "https://www.reddit.com/oembed",
  tiktok: "https://www.tiktok.com/oembed",
  x: "https://publish.twitter.com/oembed",
  youtube: "https://www.youtube.com/oembed",
};
const MAX_SOCIAL_READ_RESULT_BYTES = 900;

function telegramPreviewUrl(value) {
  const url = new URL(value);
  const segments = url.pathname.split("/").filter(Boolean);
  const channel = segments[0] === "s" ? segments[1] : segments[0];
  const message = segments[0] === "s" ? segments[2] : segments[1];
  if (
    /^[A-Za-z][A-Za-z0-9_]{3,}$/.test(channel ?? "") &&
    (!message || /^\d+$/.test(message))
  ) {
    url.host = "t.me";
    url.pathname = `/s/${channel}${message ? `/${message}` : ""}`;
  }
  return url.href;
}

function normalizedOembed(platform, originalUrl, value) {
  return {
    platform,
    url: originalUrl,
    title: cleanSocial(value.title, 500),
    content: cleanSocial(value.html),
    author: cleanSocial(value.author_name, 200),
    provider: `${platform}-public-oembed`,
  };
}

function addBoundedField(result, key, value, maximumCharacters) {
  const source = String(value ?? "").slice(0, maximumCharacters);
  let low = 0;
  let high = source.length;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    result[key] = source.slice(0, middle);
    if (
      Buffer.byteLength(JSON.stringify(result)) <= MAX_SOCIAL_READ_RESULT_BYTES
    )
      low = middle;
    else high = middle - 1;
  }
  result[key] = source.slice(0, low);
  return low < String(value ?? "").length;
}

function compactSocialResult(value) {
  const result = {
    platform: cleanSocial(value.platform, 32),
    provider: cleanSocial(value.provider, 80),
    truncated: value.truncated === true,
    ...(value.cached === true ? { cached: true } : {}),
    ...(value.stale === true ? { stale: true } : {}),
    url: "",
    title: "",
    author: "",
    content: "",
  };
  let truncated = addBoundedField(result, "url", value.url, 300);
  truncated = addBoundedField(result, "title", value.title, 200) || truncated;
  truncated = addBoundedField(result, "author", value.author, 100) || truncated;
  truncated =
    addBoundedField(result, "content", value.content, 400) || truncated;
  if (truncated) result.truncated = true;
  return result;
}

async function readOembed(service, platform, originalUrl, options) {
  const endpoint = new URL(OEMBED_ENDPOINTS[platform]);
  endpoint.searchParams.set("url", originalUrl);
  endpoint.searchParams.set("format", "json");
  if (platform === "x") {
    endpoint.searchParams.set("dnt", "true");
    endpoint.searchParams.set("omit_script", "true");
  }
  const response = await service.readText(
    {
      url: endpoint.href,
      accept: "application/json",
      cache_namespace: `social-read-${platform}`,
      max_chars: 128_000,
      attempts: 1,
    },
    options,
  );
  return normalizedOembed(platform, originalUrl, JSON.parse(response.text));
}

async function readPage(service, platform, originalUrl, maximum, options) {
  const requestedUrl =
    platform === "telegram" ? telegramPreviewUrl(originalUrl) : originalUrl;
  const page = await service.fetchPage(
    { url: requestedUrl, max_chars: maximum, reader: "auto" },
    options,
  );
  return {
    platform,
    url: page.url,
    title: cleanSocial(page.title, 500),
    content: cleanSocial(page.text, maximum),
    provider: page.reader_used ? "alta-public-reader" : "alta-public-page",
    cached: page.cached,
    stale: page.stale === true,
    truncated: page.truncated,
  };
}

export async function readPublicSocialUrl(service, args, options) {
  const rawUrl = String(args.url ?? "").trim();
  if (!rawUrl || rawUrl.length > 2_000)
    throw Object.assign(new Error("url must contain 1-2000 characters"), {
      status: 400,
      code: "alta_social_invalid_url",
    });
  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch {
    throw Object.assign(new Error("url must be a public HTTP(S) URL"), {
      status: 400,
      code: "alta_social_invalid_url",
    });
  }
  if (
    !["http:", "https:"].includes(parsed.protocol) ||
    parsed.username ||
    parsed.password ||
    parsed.port
  )
    throw Object.assign(new Error("url must be a public HTTP(S) URL"), {
      status: 400,
      code: "alta_social_invalid_url",
    });
  assertAutomatedSitePolicy(parsed);
  const originalUrl = parsed.href;
  const platform = platformForUrl(originalUrl);
  if (platform === "web")
    throw Object.assign(new Error("URL is not a supported social platform"), {
      status: 400,
      code: "alta_social_unsupported_url",
    });
  const maximum = boundedInteger(args.max_chars, 2_000, 1_000, 4_000);
  const value = await runSource(
    service,
    "social-read",
    platform,
    options,
    async (sourceOptions) => {
      if (OEMBED_ENDPOINTS[platform]) {
        try {
          return await readOembed(
            service,
            platform,
            originalUrl,
            sourceOptions,
          );
        } catch (error) {
          if (sourceOptions?.signal?.aborted) throw error;
        }
      }
      return readPage(service, platform, originalUrl, maximum, sourceOptions);
    },
    { intervalMs: 500, deadlineMs: 12_000 },
  );
  return compactSocialResult(value);
}
