function cappedInteger(value, fallback, minimum, maximum) {
  const parsed = Number(value ?? fallback);
  return Number.isFinite(parsed)
    ? Math.trunc(Math.min(Math.max(parsed, minimum), maximum))
    : fallback;
}

function normalizeDomains(values) {
  if (!Array.isArray(values)) return [];
  return [
    ...new Set(
      values.map((value) => String(value).trim().toLowerCase()).filter(Boolean),
    ),
  ].slice(0, 5);
}

function filteredQuery(args) {
  return [
    args.query,
    ...args.allowed.map((domain) => `site:${domain}`),
    ...args.excluded.map((domain) => `-site:${domain}`),
  ].join(" ");
}

function xaiText(value) {
  return (value.output ?? [])
    .filter((item) => item?.type === "message")
    .flatMap((item) => item.content ?? [])
    .filter((item) => item?.type === "output_text")
    .map((item) => item.text ?? "")
    .join("\n");
}

function xaiSources(value, text, maximum) {
  const sources = new Map();
  const visit = (node) => {
    if (!node || typeof node !== "object") return;
    const url = node.url ?? node.source_url;
    if (typeof url === "string" && /^https?:\/\//i.test(url)) {
      sources.set(url, { url, title: node.title ?? "" });
    }
    for (const nested of Object.values(node)) visit(nested);
  };
  visit(value);
  for (const match of text.matchAll(/https?:\/\/[^\s\])}>"']+/g)) {
    if (!sources.has(match[0]))
      sources.set(match[0], { url: match[0], title: "" });
  }
  return [...sources.values()].slice(0, maximum);
}

function duckDuckGoResults(html, maximum) {
  const results = [];
  for (const match of html.matchAll(
    /<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>([\s\S]*?)<\/a>[\s\S]*?(?:class="[^"]*result__snippet[^"]*"[^>]*>([\s\S]*?)<\/a>|class="[^"]*result__snippet[^"]*"[^>]*>([\s\S]*?)<\/div>)/gi,
  )) {
    let url = match[1].replaceAll("&amp;", "&");
    try {
      const parsed = new URL(url, "https://duckduckgo.com");
      url = parsed.searchParams.get("uddg") ?? parsed.href;
    } catch {}
    const clean = (value) =>
      String(value ?? "")
        .replace(/<[^>]*>/g, " ")
        .replace(/&amp;/g, "&")
        .replace(/\s+/g, " ")
        .trim();
    results.push({
      url,
      title: clean(match[2]),
      snippets: [clean(match[3] ?? match[4])],
    });
    if (results.length >= maximum) break;
  }
  return results;
}

function bingResults(html, maximum) {
  const results = [];
  const directUrl = (value) => {
    const raw = value.replaceAll("&amp;", "&");
    try {
      const encoded = new URL(raw).searchParams.get("u");
      if (encoded?.startsWith("a1"))
        return Buffer.from(encoded.slice(2), "base64url").toString("utf8");
    } catch {}
    return raw;
  };
  for (const match of html.matchAll(
    /<li class="[^"]*b_algo[^"]*"[\s\S]*?<h2[^>]*>[\s\S]*?<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)<\/a>[\s\S]*?<p[^>]*>([\s\S]*?)<\/p>/gi,
  )) {
    const clean = (value) =>
      String(value ?? "")
        .replace(/<[^>]*>/g, " ")
        .replace(/&amp;/g, "&")
        .replace(/\s+/g, " ")
        .trim();
    results.push({
      url: directUrl(match[1]),
      title: clean(match[2]),
      snippets: [clean(match[3])],
    });
    if (results.length >= maximum) break;
  }
  return results;
}

export function normalizeSearch(args, backends) {
  const query = String(args.query ?? "").trim();
  if (!query || query.length > 400)
    throw Object.assign(new Error("query must contain 1-400 characters"), {
      status: 400,
      code: "alta_web_invalid_query",
    });
  const allowed = normalizeDomains(args.allowed_domains);
  const excluded = normalizeDomains(args.excluded_domains);
  if (allowed.length && excluded.length)
    throw Object.assign(
      new Error("allowed_domains and excluded_domains cannot be combined"),
      { status: 400, code: "alta_web_domain_filters" },
    );
  const requested = args.backend ?? "auto";
  const supported = new Set([
    "auto",
    "federated",
    "brave",
    "xai",
    "jina",
    "searxng",
    "public",
    "duckduckgo",
    "bing",
  ]);
  if (!supported.has(requested))
    throw Object.assign(new Error(`Unsupported search backend: ${requested}`), {
      status: 400,
      code: "alta_web_invalid_backend",
    });
  return {
    query,
    maximum: cappedInteger(args.max_results, 10, 1, 20),
    depth: args.depth === "deep" ? "deep" : "quick",
    allowed,
    excluded,
    freshness: args.freshness ?? "",
    language: args.language ?? "",
    backend: requested,
    available: backends,
  };
}

async function braveSearch(context, args, signal) {
  if (!context.braveKey) return null;
  const tokens = args.depth === "deep" ? 16_384 : 4_096;
  const response = await context.request(
    "https://api.search.brave.com/res/v1/llm/context",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Subscription-Token": context.braveKey,
        "Accept": "application/json",
      },
      body: JSON.stringify({
        q: filteredQuery(args),
        count: Math.min(args.depth === "deep" ? 50 : 20, args.maximum * 3),
        maximum_number_of_urls: args.maximum,
        maximum_number_of_tokens: tokens,
        maximum_number_of_tokens_per_url: Math.min(4096, tokens),
        context_threshold_mode: args.depth === "deep" ? "lenient" : "balanced",
        enable_source_metadata: true,
        ...(args.freshness ? { freshness: args.freshness } : {}),
        ...(args.language ? { search_lang: args.language } : {}),
      }),
      signal,
    },
  );
  const value = JSON.parse(response.body);
  return {
    results: (value.grounding?.generic ?? [])
      .slice(0, args.maximum)
      .map((item) => ({
        url: item.url,
        title: item.title ?? "",
        snippets: item.snippets ?? [],
        metadata: value.sources?.[item.url] ?? {},
      })),
  };
}

async function xaiSearch(context, args, signal) {
  if (!context.xaiSearch) return null;
  const filters = args.allowed.length
    ? { allowed_domains: args.allowed }
    : args.excluded.length
      ? { excluded_domains: args.excluded }
      : undefined;
  const value = await context.xaiSearch({
    query: args.query,
    depth: args.depth,
    maximum: args.maximum,
    filters,
    signal,
  });
  const answer = xaiText(value);
  return { answer, results: xaiSources(value, answer, args.maximum) };
}

async function jinaSearch(context, args, signal) {
  if (!context.jinaKey) return null;
  const url = new URL(
    `https://s.jina.ai/${encodeURIComponent(filteredQuery(args))}`,
  );
  for (const domain of args.allowed) url.searchParams.append("site", domain);
  const response = await context.request(url.href, {
    accept: "text/plain",
    headers: {
      "Authorization": `Bearer ${context.jinaKey}`,
      "X-Respond-With": "markdown",
    },
    signal,
  });
  const results = [];
  const seen = new Set();
  for (const match of response.body.matchAll(
    /\[([^\]]+)]\((https?:\/\/[^\s)]+)\)/g,
  )) {
    if (seen.has(match[2])) continue;
    seen.add(match[2]);
    results.push({ url: match[2], title: match[1], snippets: [] });
    if (results.length >= args.maximum) break;
  }
  return { answer: response.body.slice(0, 24_000), results };
}

async function searxngSearch(context, args, signal) {
  if (!context.searxngUrl) return null;
  const url = new URL(
    "search",
    context.searxngUrl.endsWith("/")
      ? context.searxngUrl
      : `${context.searxngUrl}/`,
  );
  url.searchParams.set("q", filteredQuery(args));
  url.searchParams.set("format", "json");
  if (args.language) url.searchParams.set("language", args.language);
  if (["day", "month", "year"].includes(args.freshness))
    url.searchParams.set("time_range", args.freshness);
  const response = await context.request(url.href, {
    accept: "application/json",
    signal,
    trustedOrigin: new URL(context.searxngUrl).origin,
  });
  const value = JSON.parse(response.body);
  return {
    results: (value.results ?? []).slice(0, args.maximum).map((item) => ({
      url: item.url,
      title: item.title ?? "",
      snippets: [item.content ?? ""],
      engines: item.engines ?? [],
    })),
  };
}

async function duckduckgoSearch(context, args, signal) {
  const url = new URL("https://html.duckduckgo.com/html/");
  url.searchParams.set("q", filteredQuery(args));
  const response = await context.request(url.href, { signal });
  const results = duckDuckGoResults(response.body, args.maximum);
  if (!results.length)
    throw Object.assign(
      new Error(
        "DuckDuckGo returned no parseable results; configure xAI, Brave, or SearXNG for reliable search",
      ),
      { status: 502, code: "alta_web_empty_search" },
    );
  return { results };
}

async function bingSearch(context, args, signal) {
  const url = new URL("https://www.bing.com/search");
  url.searchParams.set("q", filteredQuery(args));
  const response = await context.request(url.href, { signal });
  const results = bingResults(response.body, args.maximum);
  if (!results.length)
    throw Object.assign(new Error("Bing returned no parseable results"), {
      status: 502,
      code: "alta_web_empty_search",
    });
  return { results };
}

async function publicSearch(context, args, signal) {
  try {
    return await duckduckgoSearch(context, args, signal);
  } catch (error) {
    if (signal?.aborted) throw error;
    const result = await bingSearch(context, args, signal);
    return { ...result, fallback: "bing" };
  }
}

const SEARCHERS = {
  brave: braveSearch,
  xai: xaiSearch,
  jina: jinaSearch,
  searxng: searxngSearch,
  public: publicSearch,
  duckduckgo: duckduckgoSearch,
  bing: bingSearch,
};

function candidateBackends(context, includePublic) {
  return [
    context.braveKey && "brave",
    context.xaiSearch && "xai",
    context.jinaKey && "jina",
    context.searxngUrl && "searxng",
    includePublic && "public",
  ].filter(Boolean);
}

async function runBackend(context, backend, args, signal, force = false) {
  if (
    context.backendHealth &&
    !context.backendHealth.acquire(backend, { force })
  )
    return null;
  try {
    const value = await SEARCHERS[backend](context, args, signal);
    if (!value) return null;
    if (!value.results?.length && !String(value.answer ?? "").trim())
      throw Object.assign(new Error(`${backend} returned no search evidence`), {
        status: 502,
        code: "alta_web_empty_search",
      });
    context.backendHealth?.succeeded(backend);
    return value;
  } catch (error) {
    if (!signal?.aborted) context.backendHealth?.failed(backend, error);
    throw error;
  }
}

function mergeFederated(values, maximum) {
  const results = new Map();
  const answers = [];
  for (const { backend, value } of values) {
    if (value.answer) answers.push({ backend, answer: value.answer });
    for (const item of value.results ?? []) {
      let url;
      try {
        const parsed = new URL(item.url);
        parsed.hash = "";
        url = parsed.href;
      } catch {
        continue;
      }
      const existing = results.get(url);
      if (existing) {
        existing.backends.push(backend);
        existing.snippets = [
          ...new Set([...(existing.snippets ?? []), ...(item.snippets ?? [])]),
        ].slice(0, 4);
      } else {
        results.set(url, { ...item, url, backends: [backend] });
      }
    }
  }
  return {
    backend: "federated",
    backends: values.map(({ backend }) => backend),
    answers,
    results: [...results.values()].slice(0, maximum),
  };
}

export async function executeSearch(context, args, signal) {
  if (args.backend === "federated") {
    const candidates = candidateBackends(context, true);
    const settled = await Promise.allSettled(
      candidates.map(async (backend) => ({
        backend,
        value: await runBackend(context, backend, args, signal),
      })),
    );
    const values = settled
      .filter((item) => item.status === "fulfilled" && item.value.value)
      .map((item) => item.value);
    if (values.length) return mergeFederated(values, args.maximum);
  } else if (args.backend === "auto") {
    const attempts = [];
    for (const backend of candidateBackends(context, true)) {
      try {
        const result = await runBackend(context, backend, args, signal);
        if (result) return { ...result, backend, fallback_chain: attempts };
        attempts.push(`${backend}:circuit-open`);
      } catch (error) {
        if (signal?.aborted) throw error;
        attempts.push(backend);
      }
    }
  } else {
    const result = SEARCHERS[args.backend]
      ? await runBackend(context, args.backend, args, signal, true)
      : null;
    if (result) return { ...result, backend: args.backend };
  }
  throw Object.assign(
    new Error(`Search backend "${args.backend}" is unavailable`),
    { status: 503, code: "alta_web_backend_unavailable" },
  );
}
