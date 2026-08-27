import test from "node:test";
import assert from "node:assert/strict";
import { BackendHealth } from "../internet/backend-health.mjs";
import { extractReaderDocument } from "../internet/reader.mjs";
import { executeSearch } from "../internet/search.mjs";
import { InternetService } from "../internet/service.mjs";
import { parseFeed, parseSitemapXml } from "../internet/plugins/discovery.mjs";
import { isoDate, parseCsv } from "../internet/plugins/finance-shared.mjs";
import {
  executeInternetTool,
  internetPluginIds,
  internetToolDefinitions,
  internetToolNames,
} from "../internet/plugins/registry.mjs";

const publicLookup = async () => [{ address: "93.184.216.34", family: 4 }];

test("shared plugins register fifteen unique read-only tools", () => {
  assert.deepEqual(internetPluginIds(), [
    "alta-core-web",
    "alta-deep-research",
    "alta-open-web-discovery",
    "alta-scholarly-discovery",
    "alta-public-social-discovery",
    "alta-global-news-discovery",
    "alta-public-finance-data",
    "alta-tradingview-navigation",
    "alta-local-file-reading",
  ]);
  assert.deepEqual(internetToolNames(), [
    "alta_web_search",
    "alta_web_fetch",
    "alta_web_crawl",
    "alta_web_research",
    "alta_web_batch_fetch",
    "alta_web_sitemap",
    "alta_web_feed",
    "alta_web_archive",
    "alta_academic_search",
    "alta_social_search",
    "alta_social_read",
    "alta_news_search",
    "alta_finance_data",
    "alta_tradingview_navigate",
    "alta_file_read",
  ]);
  const finance = internetToolDefinitions().find(
    (tool) => tool.name === "alta_finance_data",
  );
  const tradingView = internetToolDefinitions().find(
    (tool) => tool.name === "alta_tradingview_navigate",
  );
  assert.deepEqual(tradingView.annotations, {
    readOnlyHint: true,
    destructiveHint: false,
    idempotentHint: true,
    openWorldHint: true,
  });
  assert.deepEqual(finance.inputSchema.properties.source.enum, [
    "nasdaq",
    "coinbase",
    "worldbank",
    "treasury",
    "sec",
    "fred",
    "bls",
    "nyfed",
    "ecb",
    "imf",
    "oecd",
    "sec_xbrl",
    "fdic",
    "cftc",
    "boc",
    "eurostat",
    "kraken",
  ]);
  assert(Buffer.byteLength(JSON.stringify(finance)) <= 3_000);
  for (const definition of internetToolDefinitions())
    assert(
      Buffer.byteLength(JSON.stringify(definition)) <= 3_000,
      `${definition.name} tool definition exceeds 3 KB`,
    );
  assert(
    Buffer.byteLength(JSON.stringify(internetToolDefinitions())) <= 16_384,
    "complete internet tool catalog exceeds 16 KiB",
  );
});

test("TradingView navigation is bounded display-only routing", async () => {
  const navigate = (args) =>
    executeInternetTool(
      { recordTool: () => {} },
      "alta_tradingview_navigate",
      args,
      {},
    );
  const expected = (action, url, symbol) => ({
    source: "tradingview",
    mode: "display_only_navigation",
    action,
    ...(symbol ? { symbol } : {}),
    url,
    machine_data_tools: ["alta_finance_data", "alta_news_search"],
    notice:
      "Open this page for human-readable display; do not send it to ALTA fetch, batch-fetch, crawl, research, sitemap, feed, social-read, or archive tools.",
  });
  const chart = await navigate({
    action: "chart",
    symbol: "nasdaq:aapl",
    interval: "D",
  });
  assert.deepEqual(chart, {
    ...expected(
      "chart",
      "https://www.tradingview.com/chart/?symbol=NASDAQ%3AAAPL&interval=D",
      "NASDAQ:AAPL",
    ),
  });

  for (const [action, path] of [
    ["symbol", ""],
    ["technicals", "technicals/"],
    ["symbol_ideas", "ideas/"],
    ["symbol_news", "news/"],
    ["financials", "financials-overview/"],
    ["income", "financials-income-statement/"],
    ["balance", "financials-balance-sheet/"],
    ["cash_flow", "financials-cash-flow/"],
    ["statistics", "financials-statistics-and-ratios/"],
    ["dividends", "financials-dividends/"],
    ["financial_earnings", "financials-earnings/"],
    ["revenue", "financials-revenue/"],
    ["earnings", "earnings/"],
    ["forecast", "forecast/"],
    ["actuals", "forecast-actuals-and-estimates/"],
    ["seasonals", "seasonals/"],
    ["options", "options/"],
  ])
    assert.deepEqual(
      await navigate({ action, symbol: "nasdaq:aapl" }),
      expected(
        action,
        `https://www.tradingview.com/symbols/NASDAQ-AAPL/${path}`,
        "NASDAQ:AAPL",
      ),
    );

  for (const [action, path] of [
    ["economic_calendar", "economic-calendar/"],
    ["earnings_global", "earnings-calendar/"],
    ["revenue_calendar", "revenue-calendar/"],
    ["dividends_global", "dividend-calendar/"],
    ["ipo_calendar", "ipo-calendar/"],
    ["screener", "screener/"],
    ["crypto_screener", "crypto-coins-screener/"],
    ["etf_screener", "etf-screener/"],
    ["bond_screener", "bond-screener/"],
    ["cex_screener", "cex-screener/"],
    ["dex_screener", "dex-screener/"],
    ["stock_heatmap", "heatmap/stock/"],
    ["etf_heatmap", "heatmap/etf/"],
    ["crypto_heatmap", "heatmap/crypto/"],
    ["yield_curves", "yield-curves/"],
    ["macro_maps", "macro-maps/"],
    ["news", "news/"],
    ["community", "ideas/"],
    ["markets", "markets/"],
    ["crypto", "markets/cryptocurrencies/"],
    ["forex", "markets/currencies/"],
    ["futures", "markets/futures/"],
    ["bonds", "markets/bonds/"],
    ["etfs", "markets/etfs/"],
    ["world_economy", "markets/world-economy/"],
    ["economy_indicators", "markets/world-economy/indicators/"],
    ["economy_heatmap", "markets/world-economy/indicators-heatmap/"],
  ])
    assert.deepEqual(
      await navigate({ action }),
      expected(action, `https://www.tradingview.com/${path}`),
    );

  assert.deepEqual(
    await navigate({ action: "earnings_calendar" }),
    expected(
      "earnings_calendar",
      "https://www.tradingview.com/markets/stocks-usa/earnings/",
    ),
  );
  assert.deepEqual(
    await navigate({
      action: "dividends_calendar",
      locale: "china",
      market: "hong_kong",
    }),
    expected(
      "dividends_calendar",
      "https://cn.tradingview.com/markets/stocks-hong-kong/dividends/",
    ),
  );
  const intervals = [
    "1T",
    "10T",
    "100T",
    "1000T",
    "1S",
    "5S",
    "10S",
    "15S",
    "30S",
    "45S",
    "1",
    "2",
    "3",
    "5",
    "10",
    "15",
    "30",
    "45",
    "60",
    "120",
    "180",
    "240",
    "D",
    "W",
    "M",
    "3M",
    "6M",
    "12M",
  ];
  for (const interval of intervals)
    assert.equal(
      new URL(
        (await navigate({ action: "chart", symbol: "NYSE:IBM", interval })).url,
      ).searchParams.get("interval"),
      interval,
    );
  const bundle = await navigate({
    action: "bundle",
    symbol: "NASDAQ:AAPL",
    interval: "60",
  });
  assert.deepEqual(bundle, {
    source: "tradingview",
    mode: "display_only_navigation",
    action: "bundle",
    base_url: "https://www.tradingview.com/symbols/NASDAQ-AAPL/",
    chart_url:
      "https://www.tradingview.com/chart/?symbol=NASDAQ%3AAAPL&interval=60",
    pages: {
      overview: "",
      technicals: "technicals/",
      financials: "financials-overview/",
      forecast: "forecast/",
      news: "news/",
    },
    machine_data_tools: ["alta_finance_data", "alta_news_search"],
    notice: "Open manually; do not pass TradingView URLs to ALTA readers.",
  });
  assert(Buffer.byteLength(JSON.stringify(chart)) <= 900);
  assert(Buffer.byteLength(JSON.stringify(bundle)) <= 900);
  const maximumBundle = await navigate({
    action: "bundle",
    symbol: `${"A".repeat(24)}:B${"^".repeat(63)}`,
    interval: "1000T",
  });
  assert.deepEqual(maximumBundle.pages, {
    overview: "",
    technicals: "technicals/",
    financials: "financials-overview/",
    forecast: "forecast/",
    news: "news/",
  });
  assert(Buffer.byteLength(JSON.stringify(maximumBundle)) <= 900);
  assert.equal(
    (
      await navigate({
        action: "symbol",
        symbol: `${"A".repeat(24)}:${"B".repeat(64)}`,
      })
    ).symbol.length,
    89,
  );
  for (const args of [
    { action: "unknown" },
    { action: "chart" },
    { action: "chart", symbol: "https://evil.test/" },
    { action: "chart", symbol: `${"A".repeat(25)}:B` },
    { action: "chart", symbol: `A:${"B".repeat(65)}` },
    { action: "chart", symbol: ` ${"A".repeat(24)}:${"B".repeat(64)} ` },
    { action: "chart", symbol: "A:BTC/USD" },
    { action: "chart", symbol: "NYSE:IBM", interval: "90" },
    { action: "symbol", symbol: "NYSE:IBM", interval: "D" },
    { action: "news", symbol: "NYSE:IBM" },
    { action: "news", market: "usa" },
    { action: "news", locale: "canada" },
    { action: "news", locale: "toString" },
    { action: "earnings_calendar", market: "canada" },
    { action: "earnings_calendar", market: "__proto__" },
    { action: "news", extra: true },
  ])
    await assert.rejects(() => navigate(args), {
      code: "alta_tradingview_invalid_argument",
    });
});

test("sitemap and feed parsers return bounded normalized records", () => {
  assert.deepEqual(
    parseSitemapXml(
      "<urlset><url><loc>https://example.test/a&amp;b</loc></url></urlset>",
      "https://example.test/sitemap.xml",
    ),
    { kind: "urlset", locations: ["https://example.test/a&b"] },
  );
  assert.deepEqual(
    parseFeed(
      `<feed><entry><title>Release</title><link href="/release"/><updated>2026-08-15</updated><summary>New &amp; useful</summary></entry></feed>`,
      "https://example.test/feed.xml",
      5,
    ),
    [
      {
        title: "Release",
        url: "https://example.test/release",
        published: "2026-08-15",
        author: "",
        summary: "New & useful",
      },
    ],
  );
});

test("finance CSV and date parsing stay exact and bounded", () => {
  const csv =
    'code,label,note\r\nA,"quoted, label","line one\nline two"\r\nB,last,no-newline';
  assert.deepEqual(parseCsv(csv, 1), [
    { code: "A", label: "quoted, label", note: "line one\nline two" },
  ]);
  assert.deepEqual(parseCsv(csv, 2), [
    { code: "A", label: "quoted, label", note: "line one\nline two" },
    { code: "B", label: "last", note: "no-newline" },
  ]);
  assert.equal(isoDate("2024-02-29"), "2024-02-29");
  assert.throws(() => isoDate("2026-02-29"), /YYYY-MM-DD/);
});

test("reader adapter extracts frontmatter, markdown, and links", () => {
  assert.deepEqual(
    extractReaderDocument(
      `---\ntitle: "Rendered page"\ndescription: "Dynamic content"\nurl: "https://example.test/"\n---\n# Body\n[Docs](https://example.test/docs)`,
      "https://example.test/",
    ),
    {
      kind: "reader-markdown",
      title: "Rendered page",
      text: "# Body\n[Docs](https://example.test/docs)",
      links: [{ url: "https://example.test/docs", text: "Docs" }],
      metadata: {
        description: "Dynamic content",
        source_url: "https://example.test/",
      },
    },
  );
});

test("web fetch automatically falls back to the bounded reader adapter", async () => {
  const calls = [];
  const service = new InternetService({
    lookup: publicLookup,
    fetchImpl: async (url) => {
      calls.push(String(url));
      if (new URL(url).hostname === "r.jina.ai")
        return new Response(
          `---\ntitle: "Rendered"\nurl: "https://example.test/app"\n---\n# Rendered body\nUseful dynamic content.`,
          { headers: { "Content-Type": "text/plain" } },
        );
      return new Response(
        "<html><title>Shell</title><body>enable javascript</body></html>",
        {
          headers: { "Content-Type": "text/html" },
        },
      );
    },
    settings: {
      cacheBytes: 1024 * 1024,
      cacheTtlMs: 60_000,
      concurrency: 2,
      queueLimit: 2,
      timeoutMs: 5_000,
      maxDownloadBytes: 64 * 1024,
      maxOutputChars: 32_000,
      readerEnabled: true,
      readerMinimumChars: 500,
    },
  });
  const page = await service.fetchPage({ url: "https://example.test/app" });
  assert.equal(page.reader_used, true);
  assert.equal(page.title, "Rendered");
  assert.match(page.text, /Useful dynamic content/);
  assert.equal(calls.length, 2);
  service.close();
});

test("automatic search fails over and federated search deduplicates sources", async () => {
  const context = {
    braveKey: "test-secret",
    xaiSearch: async () => ({
      output: [
        {
          type: "message",
          content: [
            {
              type: "output_text",
              text: "Answer https://example.test/source",
            },
          ],
        },
      ],
    }),
    request: async () => ({ body: JSON.stringify({ grounding: {} }) }),
  };
  const base = {
    query: "evidence",
    maximum: 5,
    depth: "deep",
    allowed: [],
    excluded: [],
    freshness: "",
    language: "",
  };
  const automatic = await executeSearch(context, { ...base, backend: "auto" });
  assert.equal(automatic.backend, "xai");
  assert.deepEqual(automatic.fallback_chain, ["brave"]);

  context.request = async () => ({
    body: JSON.stringify({
      grounding: {
        generic: [
          {
            url: "https://example.test/source",
            title: "Source",
            snippets: ["Brave excerpt"],
          },
        ],
      },
    }),
  });
  const federated = await executeSearch(context, {
    ...base,
    backend: "federated",
  });
  assert.equal(federated.backend, "federated");
  assert.deepEqual(federated.results[0].backends, ["brave", "xai"]);
});

test("research and archive plugins compose service capabilities", async () => {
  const recorded = [];
  const service = {
    lookup: publicLookup,
    settings: { allowProxyFakeIp: false },
    recordTool: (name, succeeded) => recorded.push({ name, succeeded }),
    search: async ({ query }) => ({
      backend: "test",
      results: [
        {
          url: "https://example.test/source",
          title: query,
          snippets: ["evidence"],
        },
      ],
    }),
    fetchPage: async ({ url }) => ({
      url,
      title: "Source",
      text: "page evidence",
      metadata: {},
      reader_used: false,
    }),
    readText: async ({ url }) => {
      return {
        url,
        text: JSON.stringify([
          [
            "timestamp",
            "original",
            "statuscode",
            "mimetype",
            "digest",
            "length",
          ],
          [
            "20200102030405",
            "https://example.test/",
            "200",
            "text/html",
            "abc",
            "12",
          ],
        ]),
      };
    },
  };
  const research = await executeInternetTool(
    service,
    "alta_web_research",
    { queries: ["query one", "query two"], max_pages: 1 },
    {},
  );
  assert.equal(research.sources.length, 1);
  assert.equal(research.pages.length, 1);

  const archive = await executeInternetTool(
    service,
    "alta_web_archive",
    { url: "https://example.test/", provider: "wayback", limit: 5 },
    {},
  );
  assert.equal(
    archive.captures[0].snapshot_url,
    "https://web.archive.org/web/20200102030405/https://example.test/",
  );

  assert.deepEqual(recorded, [
    { name: "alta_web_research", succeeded: true },
    { name: "alta_web_archive", succeeded: true },
  ]);
});

test("academic plugin federates metadata, deduplicates DOI records, and keeps partial results", async () => {
  const service = {
    openAlexKey: null,
    crossrefMailto: null,
    backendHealth: new BackendHealth(),
    recordTool: () => {},
    readText: async ({ url }) => {
      const host = new URL(url).hostname;
      if (host === "api.openalex.org")
        return {
          text: JSON.stringify({
            results: [
              {
                id: "https://openalex.org/W1",
                doi: "https://doi.org/10.1000/shared",
                display_name: "Shared discovery",
                publication_date: "2026-01-02",
                authorships: [{ author: { display_name: "Ada Researcher" } }],
                primary_location: {
                  landing_page_url: "https://doi.org/10.1000/shared",
                  source: { display_name: "Journal" },
                },
                cited_by_count: 12,
                open_access: { is_oa: true },
              },
            ],
          }),
        };
      if (host === "api.crossref.org")
        return {
          text: JSON.stringify({
            message: {
              items: [
                {
                  "DOI": "10.1000/shared",
                  "URL": "https://doi.org/10.1000/shared",
                  "title": ["Shared discovery"],
                  "author": [{ given: "Ada", family: "Researcher" }],
                  "published": { "date-parts": [[2026, 1, 2]] },
                  "container-title": ["Journal"],
                  "abstract": "<jats:p>Verified abstract</jats:p>",
                  "is-referenced-by-count": 9,
                },
              ],
            },
          }),
        };
      if (host === "export.arxiv.org")
        return {
          url,
          text: `<feed><entry><title>Independent preprint</title><link href="https://arxiv.org/abs/2601.00001"/><published>2026-01-03</published><author><name>Grace Scientist</name></author><summary>Preprint evidence</summary></entry></feed>`,
        };
      throw new Error("unexpected source");
    },
  };

  const result = await executeInternetTool(
    service,
    "alta_academic_search",
    { query: "agent reliability", max_results: 5, from_year: 2025 },
    {},
  );

  assert.equal(result.result_count, 2);
  assert.deepEqual(result.results[0].sources, ["openalex", "crossref"]);
  assert.equal(result.results[0].abstract, "Verified abstract");
  assert.equal(result.results[1].source, "arxiv");
  assert.equal(result.partial, false);
});

test("social search federates direct public APIs with domain discovery", async () => {
  const service = {
    backendHealth: new BackendHealth(),
    lemmyUrl: "https://lemmy.test",
    mastodonUrl: "https://mastodon.test",
    recordTool: () => {},
    readText: async ({ url }) => {
      const parsed = new URL(url);
      if (parsed.hostname === "public.api.bsky.app")
        return {
          text: JSON.stringify({
            posts: [
              {
                uri: "at://did:plc:test/app.bsky.feed.post/post1",
                author: { handle: "agent.test", displayName: "Agent" },
                record: {
                  text: "Public Bluesky evidence",
                  createdAt: "2026-08-19",
                },
                likeCount: 3,
              },
            ],
          }),
        };
      if (parsed.hostname === "hn.algolia.com")
        return {
          text: JSON.stringify({
            hits: [
              {
                objectID: "42",
                title: "Public HN evidence",
                author: "researcher",
                created_at: "2026-08-19",
              },
            ],
          }),
        };
      if (parsed.hostname === "lemmy.test")
        return {
          text: JSON.stringify({
            posts: [
              {
                post: { id: 7, name: "Public Lemmy evidence" },
                creator: { name: "lemmy-user" },
                community: { name: "technology" },
                counts: { score: 4, comments: 2 },
              },
            ],
          }),
        };
      if (parsed.hostname === "mastodon.test")
        return {
          text: JSON.stringify([
            {
              url: "https://mastodon.test/@agent/1",
              content: "<p>Public Mastodon evidence</p>",
              account: { acct: "agent@mastodon.test" },
              created_at: "2026-08-19",
            },
          ]),
        };
      if (parsed.hostname === "www.reddit.com")
        return {
          url,
          text: `<feed><entry><title>Public Reddit evidence</title><link href="https://www.reddit.com/r/agents/comments/1/test"/><updated>2026-08-19T12:00:00Z</updated><author><name>reddit-user</name></author><summary>Public post</summary></entry></feed>`,
        };
      throw new Error(`unexpected public source: ${parsed.hostname}`);
    },
    search: async ({ allowed_domains: domains }) => ({
      backend: "test",
      results: [
        {
          url: `https://${domains[0]}/public-result`,
          title: `Web result from ${domains[0]}`,
          snippets: ["Public indexed evidence"],
        },
      ],
    }),
  };

  const result = await executeInternetTool(
    service,
    "alta_social_search",
    {
      query: "agent systems",
      hashtag: "agents",
      web_fallback: true,
      platforms: ["bluesky", "hackernews", "lemmy", "mastodon", "reddit"],
      max_results: 10,
    },
    {},
  );

  assert.deepEqual(result.sources, [
    "bluesky",
    "hackernews",
    "lemmy",
    "mastodon",
    "reddit",
    "web-1",
    "web-2",
  ]);
  assert.equal(
    result.results.some((item) => item.platform === "reddit"),
    true,
  );
  assert.equal(
    result.results.some((item) => item.platform === "bluesky"),
    true,
  );
  assert.equal(result.partial, false);
});

test("news search preserves global and primary-source partial independence", async () => {
  const service = {
    backendHealth: new BackendHealth(),
    recordTool: () => {},
    readText: async ({ url }) => {
      const host = new URL(url).hostname;
      if (host === "api.gdeltproject.org")
        return {
          text: JSON.stringify({
            articles: [
              {
                title: "Global market evidence",
                url: "https://publisher.test/global",
                domain: "publisher.test",
                seendate: "20260819T120000Z",
              },
            ],
          }),
        };
      if (host === "news.google.com")
        return {
          url,
          text: `<rss><channel><item><title>Regional market evidence</title><link>https://regional.test/story</link><pubDate>Wed, 19 Aug 2026 12:00:00 GMT</pubDate></item></channel></rss>`,
        };
      if (host === "www.bing.com")
        return {
          url,
          text: `<rss><channel><item><title>Independent market evidence</title><link>https://independent.test/story</link><pubDate>${new Date().toUTCString()}</pubDate></item></channel></rss>`,
        };
      throw new Error(`unexpected news source: ${host}`);
    },
    search: async () => ({
      backend: "test",
      results: [
        {
          title: "SEC primary evidence",
          url: "https://www.sec.gov/news/example",
          snippets: ["Official release"],
        },
      ],
    }),
  };

  const result = await executeInternetTool(
    service,
    "alta_news_search",
    { query: "market structure", timespan: "1d", max_results: 10 },
    {},
  );

  assert.deepEqual(result.sources, [
    "gdelt",
    "google_news",
    "bing_news",
    "official_finance",
  ]);
  assert.deepEqual(
    result.results.map((item) => item.source),
    ["gdelt", "google_news", "bing_news", "official_finance"],
  );
  assert.equal(result.partial, false);
});

test("finance data normalizes five login-free public sources", async () => {
  const service = {
    backendHealth: new BackendHealth(),
    secUserAgent: "ALTA test contact@example.test",
    recordTool: () => {},
    readText: async ({ url }) => {
      const parsed = new URL(url);
      if (parsed.hostname === "api.nasdaq.com") {
        const data = parsed.pathname.endsWith("/info")
          ? {
              primaryData: {
                lastSalePrice: "$100.00",
                netChange: "+1.00",
                percentageChange: "+1.00%",
                volume: "1000",
                lastTradeTimestamp: "Aug 19, 2026",
                isRealTime: false,
              },
            }
          : {
              tradesTable: {
                rows: [
                  {
                    date: "08/19/2026",
                    close: "$100.00",
                    volume: "1000",
                    open: "$99.00",
                    high: "$101.00",
                    low: "$98.00",
                  },
                ],
              },
            };
        return { text: JSON.stringify({ status: { rCode: 200 }, data }) };
      }
      if (parsed.hostname === "api.exchange.coinbase.com")
        return parsed.pathname.endsWith("/ticker")
          ? {
              text: JSON.stringify({
                price: "60000",
                bid: "59999",
                ask: "60001",
              }),
            }
          : {
              text: JSON.stringify([
                [1_776_556_800, 59000, 61000, 59500, 60000, 12],
              ]),
            };
      if (parsed.hostname === "api.worldbank.org")
        return {
          text: JSON.stringify([
            { total: 1 },
            [
              {
                country: { value: "China" },
                countryiso3code: "CHN",
                indicator: { value: "GDP" },
                date: "2025",
                value: 1,
              },
            ],
          ]),
        };
      if (parsed.hostname === "api.fiscaldata.treasury.gov")
        return {
          text: JSON.stringify({
            data: [{ record_date: "2026-08-18" }],
            meta: { count: 1 },
          }),
        };
      if (parsed.hostname === "data.sec.gov")
        return {
          text: JSON.stringify({
            name: "Example Corp",
            tickers: ["EXM"],
            exchanges: ["Nasdaq"],
            filings: {
              recent: {
                accessionNumber: ["0000000000-26-000001"],
                form: ["10-K"],
                filingDate: ["2026-08-19"],
                reportDate: ["2026-06-30"],
                primaryDocument: ["example.htm"],
                primaryDocDescription: ["Annual report"],
              },
            },
          }),
        };
      throw new Error(`unexpected finance source: ${parsed.hostname}`);
    },
  };

  const nasdaq = await executeInternetTool(
    service,
    "alta_finance_data",
    { source: "nasdaq", symbol: "EXM", from_date: "2026-08-01" },
    {},
  );
  const coinbase = await executeInternetTool(
    service,
    "alta_finance_data",
    { source: "coinbase", product: "BTC-USD", max_records: 2 },
    {},
  );
  const worldbank = await executeInternetTool(
    service,
    "alta_finance_data",
    { source: "worldbank", country: "CHN", indicator: "NY.GDP.MKTP.CD" },
    {},
  );
  const treasury = await executeInternetTool(
    service,
    "alta_finance_data",
    { source: "treasury", dataset: "avg_interest_rates" },
    {},
  );
  const sec = await executeInternetTool(
    service,
    "alta_finance_data",
    { source: "sec", cik: "1", forms: ["10-K"] },
    {},
  );

  assert.deepEqual(
    [
      nasdaq.source,
      coinbase.source,
      worldbank.source,
      treasury.source,
      sec.source,
    ],
    ["nasdaq", "coinbase", "worldbank", "treasury", "sec"],
  );
  assert.equal(nasdaq.history.length, 1);
  assert.equal(coinbase.candles.length, 1);
  assert.equal(worldbank.observations[0].country_code, "CHN");
  assert.equal(treasury.records.length, 1);
  assert.match(sec.filings[0].url, /example\.htm$/);
});

function professionalFinanceService(observed = []) {
  return {
    backendHealth: new BackendHealth(),
    secUserAgent: "ALTA test contact@example.test",
    recordTool: () => {},
    readText: async (request) => {
      const parsed = new URL(request.url);
      observed.push({
        host: parsed.hostname,
        path: parsed.pathname,
        query: Object.fromEntries(parsed.searchParams.entries()),
        accept: request.accept,
        headers: request.headers ?? {},
        max_chars: request.max_chars,
        cache_namespace: request.cache_namespace,
        attempts: request.attempts,
      });
      if (parsed.hostname === "fred.stlouisfed.org")
        return { text: "observation_date,UNRATE\n2026-07-01,4.2\n" };
      if (parsed.hostname === "api.bls.gov")
        return {
          text: JSON.stringify({
            status: "REQUEST_SUCCEEDED",
            Results: {
              series: [
                {
                  seriesID: "CUUR0000SA0",
                  data: [
                    {
                      year: "2026",
                      period: "M07",
                      periodName: "July",
                      latest: "true",
                      value: "333.918",
                      footnotes: [{}],
                    },
                  ],
                },
              ],
            },
          }),
        };
      if (parsed.hostname === "markets.newyorkfed.org")
        return {
          text: JSON.stringify({
            refRates: [
              { effectiveDate: "2026-08-18", type: "SOFR", percentRate: 3.59 },
            ],
          }),
        };
      if (parsed.hostname === "data-api.ecb.europa.eu")
        return {
          text:
            "KEY,FREQ,TIME_PERIOD,OBS_VALUE,OBS_STATUS,TITLE_COMPL,UNIT\n" +
            'EXR.D.USD.EUR.SP00.A,D,2026-08-18,1.16,A,"US dollar, ECB reference rate",USD\n',
        };
      if (parsed.hostname === "www.imf.org")
        return {
          text: JSON.stringify({
            indicators: {
              NGDP_RPCH: {
                label: "Real GDP growth",
                unit: "Annual percent change",
              },
            },
            values: { NGDP_RPCH: { USA: { 2026: 2.3 } } },
          }),
        };
      if (parsed.hostname === "sdmx.oecd.org")
        return {
          text: "REF_AREA,Reference area,TIME_PERIOD,OBS_VALUE\nUSA,United States,2026-06,100.1\n",
        };
      if (parsed.pathname.includes("/frames/"))
        return {
          text: JSON.stringify({
            label: "Assets",
            description: "Assets description",
            data: [
              {
                accn: "0001",
                cik: 320193,
                entityName: "Example Corp",
                loc: "US-CA",
                end: "2025-12-31",
                val: 200,
              },
              { accn: "0002", cik: 1, entityName: "Ignored", val: 1 },
            ],
          }),
        };
      if (parsed.hostname === "data.sec.gov")
        return {
          text: JSON.stringify({
            cik: 320193,
            entityName: "Example Corp",
            taxonomy: "us-gaap",
            tag: "Revenues",
            label: "Revenue",
            description: "Revenue description",
            units: {
              USD: [
                {
                  start: "2025-01-01",
                  end: "2025-12-31",
                  val: 100,
                  form: "10-K",
                  filed: "2026-02-01",
                },
              ],
            },
          }),
        };
      if (parsed.hostname === "api.fdic.gov")
        return {
          text: JSON.stringify({
            meta: { total: 1 },
            data: [{ data: { NAME: "Example Bank", CERT: 1, ASSET: 10 } }],
            totals: { count: 1 },
          }),
        };
      if (parsed.hostname === "publicreporting.cftc.gov")
        return {
          text: JSON.stringify([
            {
              market_and_exchange_names: "U.S. TREASURY BONDS - CBT",
              report_date_as_yyyy_mm_dd: "2026-08-11T00:00:00.000",
              open_interest_all: "100",
            },
          ]),
        };
      throw new Error(
        `unexpected professional finance source: ${parsed.hostname}`,
      );
    },
  };
}

test("finance data normalizes six official macro and central-bank sources", async () => {
  const observed = [];
  const service = professionalFinanceService(observed);
  const requests = [
    {
      source: "fred",
      series_id: "UNRATE",
      from_date: "2026-01-01",
      to_date: "2026-08-19",
    },
    { source: "bls", series_id: "CUUR0000SA0" },
    {
      source: "nyfed",
      rate_type: "sofr",
      from_date: "2026-08-01",
      to_date: "2026-08-19",
    },
    {
      source: "ecb",
      dataflow: "EXR",
      key: "D.USD.EUR.SP00.A",
      from_period: "2026-08-01",
      to_period: "2026-08-19",
    },
    {
      source: "imf",
      indicator: "NGDP_RPCH",
      country: "USA",
      from_year: 2026,
      to_year: 2026,
    },
    {
      source: "oecd",
      dataflow: "OECD.SDD.STES,DSD_STES@DF_CLI",
      key: "USA.M.LI.IX._Z.AA.IX._Z.H",
      from_period: "2026-01",
      to_period: "2026-08-19",
    },
  ];
  const results = [];
  for (const request of requests)
    results.push(
      await executeInternetTool(service, "alta_finance_data", request, {}),
    );

  assert.deepEqual(results, [
    {
      source: "fred",
      series_id: "UNRATE",
      observations: [{ date: "2026-07-01", value: "4.2" }],
      provenance: {
        publisher: "Federal Reserve Bank of St. Louis",
        source_url:
          "https://fred.stlouisfed.org/graph/fredgraph.csv?id=UNRATE&cosd=2026-01-01&coed=2026-08-19",
        official: true,
        authentication: "none",
      },
    },
    {
      source: "bls",
      series_id: "CUUR0000SA0",
      observations: [
        {
          year: "2026",
          period: "M07",
          period_name: "July",
          value: "333.918",
          latest: true,
          footnotes: [],
        },
      ],
      provenance: {
        publisher: "U.S. Bureau of Labor Statistics",
        source_url:
          "https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0",
        official: true,
        authentication: "none",
      },
    },
    {
      source: "nyfed",
      rate_type: "sofr",
      rates: [{ effectiveDate: "2026-08-18", type: "SOFR", percentRate: 3.59 }],
      provenance: {
        publisher: "Federal Reserve Bank of New York",
        source_url:
          "https://markets.newyorkfed.org/api/rates/secured/sofr/search.json?startDate=2026-08-01&endDate=2026-08-19&type=rate",
        official: true,
        authentication: "none",
      },
    },
    {
      source: "ecb",
      dataflow: "EXR",
      key: "D.USD.EUR.SP00.A",
      observations: [
        {
          key: "EXR.D.USD.EUR.SP00.A",
          period: "2026-08-18",
          value: "1.16",
          status: "A",
          title: "US dollar, ECB reference rate",
          unit: "USD",
          frequency: "D",
        },
      ],
      provenance: {
        publisher: "European Central Bank",
        source_url:
          "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?startPeriod=2026-08-01&endPeriod=2026-08-19&format=csvdata",
        official: true,
        authentication: "none",
      },
    },
    {
      source: "imf",
      indicator: {
        label: "Real GDP growth",
        unit: "Annual percent change",
      },
      observations: [{ country: "USA", year: 2026, value: 2.3 }],
      provenance: {
        publisher: "International Monetary Fund",
        source_url:
          "https://www.imf.org/external/datamapper/api/v2/NGDP_RPCH/USA?periods=2026",
        official: true,
        authentication: "none",
      },
    },
    {
      source: "oecd",
      dataflow: "OECD.SDD.STES,DSD_STES@DF_CLI",
      key: "USA.M.LI.IX._Z.AA.IX._Z.H",
      records: [
        {
          reference_area_code: "USA",
          reference_area: "United States",
          period: "2026-06",
          value: "100.1",
        },
      ],
      provenance: {
        publisher: "Organisation for Economic Co-operation and Development",
        source_url:
          "https://sdmx.oecd.org/public/rest/v1/data/OECD.SDD.STES,DSD_STES@DF_CLI/USA.M.LI.IX._Z.AA.IX._Z.H?startPeriod=2026-01&endPeriod=2026-08-19&dimensionAtObservation=AllDimensions&format=csvfilewithlabels",
        official: true,
        authentication: "none",
      },
    },
  ]);
  assert.deepEqual(
    observed.map(
      ({
        host,
        path,
        accept,
        headers,
        max_chars,
        cache_namespace,
        attempts,
      }) => ({
        host,
        path,
        accept,
        headers,
        max_chars,
        cache_namespace,
        attempts,
      }),
    ),
    [
      {
        host: "fred.stlouisfed.org",
        path: "/graph/fredgraph.csv",
        accept: "text/csv",
        headers: {},
        max_chars: 512_000,
        cache_namespace: "finance-fred",
        attempts: 2,
      },
      {
        host: "api.bls.gov",
        path: "/publicAPI/v1/timeseries/data/CUUR0000SA0",
        accept: "application/json",
        headers: {},
        max_chars: 512_000,
        cache_namespace: "finance-bls",
        attempts: 1,
      },
      {
        host: "markets.newyorkfed.org",
        path: "/api/rates/secured/sofr/search.json",
        accept: "application/json",
        headers: {},
        max_chars: 512_000,
        cache_namespace: "finance-nyfed-rates",
        attempts: 2,
      },
      {
        host: "data-api.ecb.europa.eu",
        path: "/service/data/EXR/D.USD.EUR.SP00.A",
        accept: "text/csv",
        headers: {},
        max_chars: 750_000,
        cache_namespace: "finance-ecb-sdmx",
        attempts: 2,
      },
      {
        host: "www.imf.org",
        path: "/external/datamapper/api/v2/NGDP_RPCH/USA",
        accept: "application/json",
        headers: {},
        max_chars: 1_000_000,
        cache_namespace: "finance-imf-datamapper",
        attempts: 1,
      },
      {
        host: "sdmx.oecd.org",
        path: "/public/rest/v1/data/OECD.SDD.STES,DSD_STES@DF_CLI/USA.M.LI.IX._Z.AA.IX._Z.H",
        accept: "text/csv",
        headers: { "Accept-Language": "en" },
        max_chars: 1_000_000,
        cache_namespace: "finance-oecd-sdmx",
        attempts: 1,
      },
    ],
  );
  assert.deepEqual(
    observed.map((request) => request.query),
    [
      { id: "UNRATE", cosd: "2026-01-01", coed: "2026-08-19" },
      {},
      { startDate: "2026-08-01", endDate: "2026-08-19", type: "rate" },
      { startPeriod: "2026-08-01", endPeriod: "2026-08-19", format: "csvdata" },
      { periods: "2026" },
      {
        startPeriod: "2026-01",
        endPeriod: "2026-08-19",
        dimensionAtObservation: "AllDimensions",
        format: "csvfilewithlabels",
      },
    ],
  );
});

test("finance data normalizes three official regulatory sources", async () => {
  const observed = [];
  const service = professionalFinanceService(observed);
  const requests = [
    {
      source: "sec_xbrl",
      cik: "320193",
      xbrl_mode: "company_concept",
      concept: "Revenues",
    },
    { source: "fdic", dataset: "institutions", fdic_filter: "ACTIVE:1" },
    {
      source: "cftc",
      cftc_report: "tff_futures",
      market: "UST BOND",
      from_date: "2026-01-01",
      to_date: "2026-08-19",
    },
  ];
  const results = [];
  for (const request of requests)
    results.push(
      await executeInternetTool(service, "alta_finance_data", request, {}),
    );

  assert.deepEqual(
    results.map(({ provenance: _provenance, ...result }) => result),
    [
      {
        source: "sec_xbrl",
        mode: "company_concept",
        cik: 320193,
        entity: "Example Corp",
        taxonomy: "us-gaap",
        concept: "Revenues",
        label: "Revenue",
        description: "Revenue description",
        facts: [
          {
            unit: "USD",
            start: "2025-01-01",
            end: "2025-12-31",
            val: 100,
            form: "10-K",
            filed: "2026-02-01",
          },
        ],
      },
      {
        source: "fdic",
        dataset: "institutions",
        records: [{ NAME: "Example Bank", CERT: 1, ASSET: 10 }],
        metadata: { total: 1 },
        totals: { count: 1 },
      },
      {
        source: "cftc",
        report: "tff_futures",
        records: [
          {
            market_and_exchange_names: "U.S. TREASURY BONDS - CBT",
            report_date_as_yyyy_mm_dd: "2026-08-11T00:00:00.000",
            open_interest_all: "100",
          },
        ],
      },
    ],
  );
  assert.deepEqual(
    results.map((result) => ({
      publisher: result.provenance.publisher,
      official: result.provenance.official,
      authentication: result.provenance.authentication,
    })),
    [
      {
        publisher: "U.S. Securities and Exchange Commission",
        official: true,
        authentication: "none",
      },
      {
        publisher: "Federal Deposit Insurance Corporation",
        official: true,
        authentication: "none",
      },
      {
        publisher: "Commodity Futures Trading Commission",
        official: true,
        authentication: "none",
      },
    ],
  );
  assert.deepEqual(observed[0], {
    host: "data.sec.gov",
    path: "/api/xbrl/companyconcept/CIK0000320193/us-gaap/Revenues.json",
    query: {},
    accept: "application/json",
    headers: { "User-Agent": "ALTA test contact@example.test" },
    max_chars: 1_000_000,
    cache_namespace: "finance-sec-xbrl-company_concept",
    attempts: 1,
  });
  assert.deepEqual(observed[1].query, {
    filters: "ACTIVE:1",
    fields: "NAME,CERT,CITY,STNAME,ACTIVE,ASSET,DEP",
    limit: "20",
    offset: "0",
    sort_by: "ASSET",
    sort_order: "DESC",
  });
  assert.deepEqual(
    {
      host: observed[1].host,
      path: observed[1].path,
      accept: observed[1].accept,
      headers: observed[1].headers,
      max_chars: observed[1].max_chars,
      cache_namespace: observed[1].cache_namespace,
      attempts: observed[1].attempts,
    },
    {
      host: "api.fdic.gov",
      path: "/banks/institutions",
      accept: "application/json",
      headers: {},
      max_chars: 750_000,
      cache_namespace: "finance-fdic-institutions",
      attempts: 2,
    },
  );
  assert.deepEqual(
    {
      host: observed[2].host,
      path: observed[2].path,
      accept: observed[2].accept,
      headers: observed[2].headers,
      max_chars: observed[2].max_chars,
      cache_namespace: observed[2].cache_namespace,
      attempts: observed[2].attempts,
    },
    {
      host: "publicreporting.cftc.gov",
      path: "/resource/gpe5-46if.json",
      accept: "application/json",
      headers: {},
      max_chars: 750_000,
      cache_namespace: "finance-cftc-tff_futures",
      attempts: 1,
    },
  );
  assert.equal(observed[2].query.$limit, "20");
  assert.equal(observed[2].query.$order, "report_date_as_yyyy_mm_dd DESC");
  assert.match(observed[2].query.$where, /UST BOND/);
  assert.match(observed[2].query.$select, /lev_money_positions_short/);
});

test("SEC XBRL frame mode is bounded and uses the documented path", async () => {
  const observed = [];
  const service = professionalFinanceService(observed);
  const result = await executeInternetTool(
    service,
    "alta_finance_data",
    {
      source: "sec_xbrl",
      xbrl_mode: "frame",
      taxonomy: "us-gaap",
      concept: "Assets",
      unit: "USD",
      xbrl_period: "CY2025Q4I",
      max_records: 1,
    },
    {},
  );

  assert.deepEqual(result.records, [
    {
      accn: "0001",
      cik: 320193,
      entityName: "Example Corp",
      loc: "US-CA",
      end: "2025-12-31",
      val: 200,
    },
  ]);
  assert.equal(
    observed[0].path,
    "/api/xbrl/frames/us-gaap/Assets/USD/CY2025Q4I.json",
  );
  assert.deepEqual(observed[0].headers, {
    "User-Agent": "ALTA test contact@example.test",
  });
});

test("SEC regional failures degrade explicitly without masking client errors", async () => {
  const searches = [];
  const service = {
    backendHealth: new BackendHealth(),
    secUserAgent: "ALTA test contact@example.test",
    recordTool: () => {},
    readText: async () => {
      throw Object.assign(new Error("regional SEC block"), { status: 403 });
    },
    search: async (args) => {
      searches.push(args);
      return {
        results: [
          {
            title: "SEC result",
            url: "https://www.sec.gov/example",
            snippets: ["Primary"],
          },
        ],
      };
    },
  };
  const result = await executeInternetTool(
    service,
    "alta_finance_data",
    { source: "sec_xbrl", cik: "320193", concept: "Revenues" },
    {},
  );
  assert.deepEqual(result, {
    source: "sec_xbrl",
    cik: "0000320193",
    facts: [],
    fallback_results: [
      {
        title: "SEC result",
        url: "https://www.sec.gov/example",
        snippets: ["Primary"],
      },
    ],
    failures: [{ endpoint: "data.sec.gov", error: "regional SEC block" }],
    partial: true,
  });
  assert.deepEqual(searches[0].allowed_domains, ["sec.gov"]);

  let invalidSearches = 0;
  const invalidService = {
    ...service,
    backendHealth: new BackendHealth(),
    search: async () => {
      invalidSearches += 1;
      return { results: [] };
    },
  };
  await assert.rejects(
    executeInternetTool(
      invalidService,
      "alta_finance_data",
      { source: "sec_xbrl", cik: "320193" },
      {},
    ),
    (error) => error.status === 400,
  );
  assert.equal(invalidSearches, 0);

  const cancelledSearches = [];
  const controller = new AbortController();
  controller.abort(new Error("cancelled"));
  await assert.rejects(
    executeInternetTool(
      {
        ...service,
        backendHealth: new BackendHealth(),
        search: async (args) => cancelledSearches.push(args),
      },
      "alta_finance_data",
      { source: "sec", cik: "320193" },
      { signal: controller.signal },
    ),
    /regional SEC block|cancelled/,
  );
  assert.deepEqual(cancelledSearches, []);
});
