import test from "node:test";
import assert from "node:assert/strict";
import { BackendHealth } from "../internet/backend-health.mjs";
import { executeInternetTool } from "../internet/plugins/registry.mjs";

test("expanded social adapters normalize four additional public sources", async () => {
  let webSearches = 0;
  const service = {
    backendHealth: new BackendHealth(),
    peertubeUrl: "https://peertube.test",
    discourseUrl: "https://discourse.test",
    recordTool: () => {},
    readText: async ({ url }) => {
      const parsed = new URL(url);
      if (parsed.hostname === "api.stackexchange.com")
        return {
          text: JSON.stringify({
            items: [
              {
                title: "Reliable agent collaboration",
                link: "https://stackoverflow.com/questions/1/agents",
                creation_date: 1_787_097_600,
                tags: ["agents"],
                owner: { display_name: "Stack User" },
                score: 4,
                answer_count: 2,
              },
            ],
          }),
        };
      if (parsed.hostname === "peertube.test")
        return {
          text: JSON.stringify({
            data: [
              {
                uuid: "video-1",
                shortUUID: "video1",
                name: "Agent systems video",
                description: "Public federated video",
                publishedAt: "2026-08-19T12:00:00Z",
                account: { displayName: "Video Author" },
              },
            ],
          }),
        };
      if (parsed.hostname === "dev.to")
        return {
          text: JSON.stringify([
            {
              title: "Agent engineering",
              description: "Public DEV article",
              url: "https://dev.to/agent/article",
              published_at: "2026-08-19T12:00:00Z",
              tag_list: ["agents"],
              user: { username: "dev-user" },
            },
          ]),
        };
      if (parsed.hostname === "discourse.test")
        return {
          text: JSON.stringify({
            posts: [
              {
                topic_id: 7,
                username: "forum-user",
                blurb: "Public Discourse result",
                created_at: "2026-08-19T12:00:00Z",
              },
            ],
            topics: [
              {
                id: 7,
                slug: "agent-operations",
                title: "Agent operations",
                posts_count: 3,
              },
            ],
          }),
        };
      throw new Error(`unexpected social source: ${parsed.hostname}`);
    },
    search: async ({ allowed_domains: domains }) => {
      webSearches += 1;
      return {
        backend: "test",
        results: [
          {
            url: `https://${domains[0]}/indexed-result`,
            title: "Indexed public result",
            snippets: ["Domain discovery"],
          },
        ],
      };
    },
  };

  const result = await executeInternetTool(
    service,
    "alta_social_search",
    {
      query: "agents",
      hashtag: "agents",
      platforms: ["stackexchange", "peertube", "devto", "discourse"],
      max_results: 12,
    },
    {},
  );

  assert.deepEqual(result.sources.slice(0, 4), [
    "stackexchange",
    "peertube",
    "devto",
    "discourse",
  ]);
  const resultPlatforms = new Set(result.results.map((item) => item.platform));
  for (const platform of ["stackexchange", "peertube", "devto", "discourse"])
    assert.equal(resultPlatforms.has(platform), true);
  assert.equal(webSearches, 0);
  assert.equal(result.partial, false);
});

test("YouTube failover and Stocktwits streams stay login-free and source-isolated", async () => {
  const calls = [];
  const service = {
    backendHealth: new BackendHealth(),
    pipedUrls: ["https://piped-one.test", "https://piped-two.test"],
    recordTool: () => {},
    readText: async ({ url }) => {
      const parsed = new URL(url);
      calls.push(parsed.hostname);
      if (parsed.hostname === "piped-one.test")
        throw Object.assign(new Error("first instance unavailable"), {
          status: 503,
        });
      if (parsed.hostname === "piped-two.test")
        return {
          text: JSON.stringify({
            items: [
              {
                type: "stream",
                url: "javascript:alert(1)",
                title: "Unsafe scheme",
              },
              {
                type: "stream",
                url: "https://evil.example/watch?v=1",
                title: "Unsafe host",
              },
              {
                type: "stream",
                url: "//evil.example/watch?v=2",
                title: "Unsafe scheme-relative host",
              },
              {
                type: "stream",
                url: "/watch?v=video-1",
                title: "Public market briefing",
                uploaderName: "Market Channel",
                uploaded: 1_787_097_600_000,
                views: 42,
                duration: 90,
              },
            ],
          }),
        };
      if (parsed.hostname === "api.stocktwits.com")
        return {
          text: JSON.stringify({
            messages: [
              {
                id: 7,
                body: "$AAPL public market discussion",
                created_at: "2026-08-19T12:00:00Z",
                user: { username: "market-user", name: "Market User" },
                likes: { total: 3 },
                entities: { sentiment: { basic: "Bullish" } },
              },
            ],
          }),
        };
      throw new Error(`unexpected source: ${parsed.hostname}`);
    },
    search: async ({ allowed_domains: domains }) => ({
      backend: "test",
      results: [
        {
          url: `https://${domains[0]}/watch?v=indexed`,
          title: "Indexed YouTube backup",
          snippets: ["Independent discovery path"],
        },
      ],
    }),
  };

  const result = await executeInternetTool(
    service,
    "alta_social_search",
    {
      query: "market briefing",
      platforms: ["youtube", "stocktwits"],
      symbol: "AAPL",
      max_results: 6,
    },
    {},
  );

  assert.deepEqual(result.sources, ["youtube", "stocktwits", "web-1"]);
  assert.deepEqual(calls.toSorted(), [
    "api.stocktwits.com",
    "piped-one.test",
    "piped-two.test",
  ]);
  assert.equal(result.results[0].provider, "piped-piped-two.test");
  assert.equal(result.results[1].provider, "stocktwits-public-stream");
  assert.equal(result.results[2].provider, "web-test");
  assert.deepEqual(
    result.results.map(({ url }) => url),
    [
      "https://www.youtube.com/watch?v=video-1",
      "https://stocktwits.com/market-user/message/7",
      "https://youtube.com/watch?v=indexed",
    ],
  );
  assert.equal(result.partial, false);
});

test("YouTube instance deadlines fail over deterministically and preserve web evidence", async () => {
  const timeoutCalls = [];
  let timeoutCount = 0;
  const service = {
    backendHealth: new BackendHealth(),
    pipedUrls: ["https://piped-hangs.test", "https://piped-works.test"],
    timeoutSignal: (milliseconds) => {
      timeoutCalls.push(milliseconds);
      const controller = new AbortController();
      if (timeoutCount === 0)
        queueMicrotask(() => controller.abort(new Error("instance timeout")));
      timeoutCount += 1;
      return controller.signal;
    },
    recordTool: () => {},
    readText: async ({ url }, { signal }) => {
      const parsed = new URL(url);
      if (parsed.hostname === "piped-hangs.test")
        return new Promise((_, reject) => {
          if (signal.aborted) reject(signal.reason);
          else
            signal.addEventListener("abort", () => reject(signal.reason), {
              once: true,
            });
        });
      return {
        text: JSON.stringify({
          items: [
            {
              type: "stream",
              url: "/watch?v=after-timeout",
              title: "Recovered public video",
            },
          ],
        }),
      };
    },
    search: async () => ({
      backend: "test",
      results: [
        {
          url: "https://youtube.com/watch?v=backup",
          title: "Indexed backup",
          snippets: ["Public search evidence"],
        },
      ],
    }),
  };

  const result = await executeInternetTool(
    service,
    "alta_social_search",
    { query: "recovery", platforms: ["youtube"], max_results: 4 },
    {},
  );

  assert.deepEqual(timeoutCalls, [3_500, 3_500]);
  assert.deepEqual(result.sources, ["youtube", "web-1"]);
  assert.equal(result.results[0].provider, "piped-piped-works.test");
  assert.equal(result.partial, false);
});

test("YouTube keeps web results when every public instance fails", async () => {
  const service = {
    backendHealth: new BackendHealth(),
    pipedUrls: ["https://piped-one.test", "https://piped-two.test"],
    recordTool: () => {},
    readText: async () =>
      Promise.reject(
        Object.assign(new Error("instance unavailable"), {
          status: 503,
        }),
      ),
    search: async () => ({
      backend: "test",
      results: [
        {
          url: "https://youtube.com/watch?v=indexed",
          title: "Indexed public video",
          snippets: ["Web fallback"],
        },
      ],
    }),
  };

  const result = await executeInternetTool(
    service,
    "alta_social_search",
    { query: "fallback", platforms: ["youtube"], max_results: 3 },
    {},
  );

  assert.deepEqual(result.sources, ["web-1"]);
  assert.deepEqual(result.failures, [
    {
      source: "youtube",
      error: "All configured public Piped instances failed",
    },
  ]);
  assert.equal(result.results[0].provider, "web-test");
  assert.equal(result.partial, true);
});

test("Stocktwits access challenges preserve indexed public evidence", async () => {
  const allowedDomains = [];
  const service = {
    backendHealth: new BackendHealth(),
    recordTool: () => {},
    readText: async () =>
      Promise.reject(
        Object.assign(new Error("public stream blocked"), {
          status: 403,
        }),
      ),
    search: async ({ allowed_domains: domains }) => {
      allowedDomains.push(domains);
      return {
        backend: "test",
        results: [
          {
            url: "https://stocktwits.com/symbol/AAPL",
            title: "AAPL public discussion",
            snippets: ["Indexed public market posts"],
          },
        ],
      };
    },
  };

  const result = await executeInternetTool(
    service,
    "alta_social_search",
    {
      query: "Apple",
      platforms: ["stocktwits"],
      symbol: "AAPL",
      max_results: 3,
    },
    {},
  );

  assert.deepEqual(result.sources, ["web-1"]);
  assert.deepEqual(result.failures, [
    {
      source: "stocktwits",
      error: "Stocktwits public stream unavailable (HTTP 403)",
    },
  ]);
  assert.equal(result.results[0].provider, "web-test");
  assert.equal(result.partial, true);
  assert.deepEqual(allowedDomains, [["stocktwits.com"]]);
});

test("Stocktwits discovery does not infer or accept unsafe symbols", async () => {
  let directCalls = 0;
  const service = {
    backendHealth: new BackendHealth(),
    recordTool: () => {},
    readText: async () => {
      directCalls += 1;
      throw new Error("unexpected direct call");
    },
    search: async ({ allowed_domains: domains }) => {
      assert.deepEqual(domains, ["stocktwits.com"]);
      return {
        backend: "test",
        results: [
          {
            url: "https://stocktwits.com/symbol/NVDA",
            title: "NVDA discussion",
            snippets: ["Indexed only"],
          },
        ],
      };
    },
  };

  const result = await executeInternetTool(
    service,
    "alta_social_search",
    { query: "Nvidia", platforms: ["stocktwits"], max_results: 2 },
    {},
  );
  assert.equal(directCalls, 0);
  assert.deepEqual(result.sources, ["web-1"]);
  await assert.rejects(
    () =>
      executeInternetTool(
        service,
        "alta_social_search",
        {
          query: "Nvidia",
          platforms: ["stocktwits"],
          symbol: "NVDA/../../unsafe",
        },
        {},
      ),
    { code: "alta_social_invalid_symbol" },
  );
});

test("public social reader uses oEmbed and bounded page fallback without login", async () => {
  const fetched = [];
  const oembedRequests = [];
  const service = {
    backendHealth: new BackendHealth(),
    recordTool: () => {},
    readText: async ({ url }) => {
      const parsed = new URL(url);
      if (parsed.hostname === "publish.twitter.com") {
        oembedRequests.push(parsed);
        return {
          text: JSON.stringify({
            author_name: "Open Source",
            author_url: "https://x.com/open_source",
            html: "<blockquote>Public release evidence</blockquote>",
            provider_name: "X",
            type: "rich",
          }),
        };
      }
      throw Object.assign(new Error("oEmbed unavailable"), { status: 503 });
    },
    fetchPage: async ({ url, max_chars: maximum }) => {
      fetched.push({ url, maximum });
      return {
        url,
        title: "Public page",
        text: "Public fallback content",
        links: [{ url: "https://example.test/source", text: "Source" }],
        reader_used: false,
        cached: false,
        truncated: false,
      };
    },
  };

  const post = await executeInternetTool(
    service,
    "alta_social_read",
    { url: "https://x.com/open_source/status/1" },
    {},
  );
  assert.deepEqual(post, {
    platform: "x",
    provider: "x-public-oembed",
    truncated: false,
    url: "https://x.com/open_source/status/1",
    title: "",
    author: "Open Source",
    content: "Public release evidence",
  });
  assert.equal(oembedRequests.length, 1);
  assert.equal(
    oembedRequests[0].searchParams.get("url"),
    "https://x.com/open_source/status/1",
  );
  assert.equal(oembedRequests[0].searchParams.get("format"), "json");
  assert.equal(oembedRequests[0].searchParams.get("dnt"), "true");
  assert.equal(oembedRequests[0].searchParams.get("omit_script"), "true");

  const tiktok = await executeInternetTool(
    service,
    "alta_social_read",
    { url: "https://www.tiktok.com/@public/video/1", max_chars: 2_000 },
    {},
  );
  assert.equal(tiktok.provider, "alta-public-page");
  for (const url of [
    "https://t.me/public_channel",
    "https://t.me/public_channel/42",
    "https://telegram.me/public_channel/43",
    "https://t.me/s/public_channel/44",
  ]) {
    const telegram = await executeInternetTool(
      { ...service, backendHealth: new BackendHealth() },
      "alta_social_read",
      { url, max_chars: 3_000 },
      {},
    );
    assert.equal(telegram.platform, "telegram");
  }
  assert.deepEqual(fetched, [
    { url: "https://www.tiktok.com/@public/video/1", maximum: 2_000 },
    { url: "https://t.me/s/public_channel", maximum: 3_000 },
    { url: "https://t.me/s/public_channel/42", maximum: 3_000 },
    { url: "https://t.me/s/public_channel/43", maximum: 3_000 },
    { url: "https://t.me/s/public_channel/44", maximum: 3_000 },
  ]);
  const escaped = await executeInternetTool(
    {
      ...service,
      backendHealth: new BackendHealth(),
      fetchPage: async ({ url }) => ({
        url,
        title: "\u0001".repeat(1_000),
        text: `${"dense ".repeat(1_000)}${"𒀀".repeat(1_000)}`,
        links: [],
        reader_used: false,
        cached: false,
        truncated: false,
      }),
    },
    "alta_social_read",
    { url: "https://www.instagram.com/public/", max_chars: 4_000 },
    {},
  );
  assert.equal(escaped.truncated, true);
  assert(Buffer.byteLength(JSON.stringify(escaped)) <= 900);
  const unicode = await executeInternetTool(
    {
      ...service,
      backendHealth: new BackendHealth(),
      fetchPage: async ({ url }) => ({
        url,
        title: "",
        text: "𒀀".repeat(1_000),
        reader_used: false,
        cached: false,
        truncated: false,
      }),
    },
    "alta_social_read",
    { url: "https://www.instagram.com/unicode/", max_chars: 4_000 },
    {},
  );
  assert.equal(unicode.content.startsWith("𒀀"), true);
  assert.equal(unicode.truncated, true);
  assert(Buffer.byteLength(JSON.stringify(unicode)) <= 900);
  await assert.rejects(
    () =>
      executeInternetTool(
        service,
        "alta_social_read",
        { url: "https://token@x.com/public/status/1" },
        {},
      ),
    { code: "alta_social_invalid_url" },
  );
  await assert.rejects(
    () =>
      executeInternetTool(
        service,
        "alta_social_read",
        { url: "ftp://x.com/public/status/1" },
        {},
      ),
    { code: "alta_social_invalid_url" },
  );
  await assert.rejects(
    () =>
      executeInternetTool(
        service,
        "alta_social_read",
        { url: "https://x.com:8443/public/status/1" },
        {},
      ),
    { code: "alta_social_invalid_url" },
  );
  await assert.rejects(
    () =>
      executeInternetTool(
        service,
        "alta_social_read",
        { url: "https://x.com.evil.example/public/status/1" },
        {},
      ),
    { code: "alta_social_unsupported_url" },
  );
});

test("cancelled social reads do not start a page fallback", async () => {
  let pageFallbacks = 0;
  const service = {
    backendHealth: new BackendHealth(),
    recordTool: () => {},
    readText: async (_request, { signal }) => {
      if (signal.aborted) throw signal.reason;
      throw new Error("expected an aborted signal");
    },
    fetchPage: async () => {
      pageFallbacks += 1;
      throw new Error("unexpected page fallback");
    },
  };
  const controller = new AbortController();
  controller.abort(new Error("parent cancelled"));

  await assert.rejects(
    () =>
      executeInternetTool(
        service,
        "alta_social_read",
        { url: "https://x.com/public/status/1" },
        { signal: controller.signal },
      ),
    /parent cancelled/,
  );
  assert.equal(pageFallbacks, 0);
});

test("expanded news federation combines aggregators, Wikinews, publishers, and institutions", async () => {
  const now = new Date().toISOString();
  const rss = (title, link) =>
    `<rss><channel><item><title>${title}</title><link>${link}</link><pubDate>${new Date().toUTCString()}</pubDate><description>Climate policy evidence</description></item></channel></rss>`;
  const service = {
    backendHealth: new BackendHealth(),
    recordTool: () => {},
    readText: async ({ url }) => {
      const parsed = new URL(url);
      if (parsed.hostname === "www.bing.com")
        return {
          url,
          text: rss("Bing climate report", "https://publisher.test/bing"),
        };
      if (parsed.hostname === "en.wikinews.org")
        return {
          text: JSON.stringify({
            query: {
              search: [
                {
                  title: "Climate policy",
                  snippet: "Public Wikinews evidence",
                  timestamp: now,
                },
              ],
            },
          }),
        };
      if (parsed.hostname === "feeds.bbci.co.uk")
        return {
          url,
          text: parsed.pathname.includes("zhongwen")
            ? rss("气候政策 climate", "https://bbc.test/zh")
            : rss("Climate policy", "https://bbc.test/world"),
        };
      throw new Error(`unexpected news source: ${parsed.hostname}`);
    },
    search: async () => ({
      backend: "test",
      results: [
        {
          title: "UN climate release",
          url: "https://www.un.org/climate-release",
          snippets: ["Primary institutional evidence"],
        },
      ],
    }),
  };

  const result = await executeInternetTool(
    service,
    "alta_news_search",
    {
      query: "climate",
      timespan: "1d",
      sources: [
        "bing_news",
        "wikinews",
        "bbc_world",
        "bbc_zh",
        "official_global",
      ],
      max_results: 15,
    },
    {},
  );

  assert.deepEqual(result.sources, [
    "bing_news",
    "wikinews",
    "bbc_world",
    "bbc_zh",
    "official_global",
  ]);
  assert.deepEqual(
    result.results.map((item) => item.source),
    ["bing_news", "wikinews", "bbc_world", "bbc_zh", "official_global"],
  );
  assert.equal(result.partial, false);
});
