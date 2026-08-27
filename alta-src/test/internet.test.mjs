import test from "node:test";
import assert from "node:assert/strict";
import {
  assertPublicUrl,
  extractHtml,
  isPublicAddress,
} from "../internet/content.mjs";
import { handleMcpMessage, internetToolNames } from "../internet/mcp.mjs";
import { InternetService } from "../internet/service.mjs";

const publicLookup = async () => [{ address: "93.184.216.34", family: 4 }];

test("public URL policy blocks local and reserved targets", async () => {
  assert.equal(isPublicAddress("8.8.8.8"), true);
  assert.equal(isPublicAddress("198.18.0.193"), false);
  assert.equal(
    isPublicAddress("198.18.0.193", { allowProxyFakeIp: true }),
    true,
  );
  for (const address of [
    "127.0.0.1",
    "10.0.0.2",
    "169.254.169.254",
    "192.168.1.1",
    "::1",
    "fd00::1",
  ]) {
    assert.equal(isPublicAddress(address), false, address);
  }
  await assert.rejects(
    () => assertPublicUrl("http://127.0.0.1/private"),
    /Private/,
  );
  for (const url of [
    "https://tradingview.com/",
    "https://cn.tradingview.com/chart/",
    "https://www.tradingview.com./chart/",
  ])
    await assert.rejects(() => assertPublicUrl(url), {
      code: "alta_web_site_policy",
    });
  for (const url of [
    "https://github.com/example/project",
    "https://api.github.com/repos/example/project",
    "https://raw.githubusercontent.com/example/project/main/file",
  ])
    await assert.rejects(() => assertPublicUrl(url, { lookup: publicLookup }), {
      code: "alta_web_repository_host_disabled",
    });
  await assert.rejects(
    () =>
      assertPublicUrl("https://example.test", {
        lookup: async () => [{ address: "10.2.3.4", family: 4 }],
      }),
    /Private/,
  );
  assert.equal(
    (
      await assertPublicUrl("https://example.test/path", {
        lookup: publicLookup,
      })
    ).href,
    "https://example.test/path",
  );
});

test("HTML extraction returns readable text and absolute crawl links", () => {
  const value = extractHtml(
    `<!doctype html><html><head><title>Example &amp; Test</title><style>hidden</style></head>
     <body><nav>menu</nav><main><h1>Heading</h1><p>Hello <b>world</b>.</p>
     <a href="/docs">Read docs</a><script>secret()</script></main></body></html>`,
    "https://example.test/start",
  );
  assert.deepEqual(value, {
    title: "Example & Test",
    text: "Heading\nHello world .\n\nRead docs",
    links: [{ url: "https://example.test/docs", text: "Read docs" }],
    metadata: {
      description: "",
      author: "",
      published_time: "",
      canonical_url: "",
      language: "",
      feeds: [],
      structured_data: [],
    },
  });
});

test("internet service fetches, bounds, caches, searches, and crawls", async () => {
  const calls = [];
  const fetchImpl = async (url) => {
    calls.push(String(url));
    const pathname = new URL(url).pathname;
    if (pathname === "/start") {
      return new Response(
        '<html><title>Start</title><main><p>alpha text</p><a href="/next">next</a><a href="https://other.test/out">out</a></main></html>',
        { headers: { "Content-Type": "text/html" } },
      );
    }
    return new Response(
      "<html><title>Next</title><main>beta text</main></html>",
      {
        headers: { "Content-Type": "text/html" },
      },
    );
  };
  let xaiCalls = 0;
  const service = new InternetService({
    fetchImpl,
    lookup: publicLookup,
    xaiSearch: async () => {
      xaiCalls += 1;
      return {
        output: [
          {
            type: "message",
            content: [
              {
                type: "output_text",
                text: "Grounded answer [source](https://source.test/page)",
                annotations: [
                  { type: "url_citation", url: "https://source.test/page" },
                ],
              },
            ],
          },
        ],
      };
    },
    settings: {
      cacheBytes: 1024 * 1024,
      cacheTtlMs: 60_000,
      concurrency: 2,
      queueLimit: 4,
      timeoutMs: 5_000,
      maxDownloadBytes: 64 * 1024,
      maxOutputChars: 32_000,
      readerEnabled: false,
    },
  });

  const first = await service.fetchPage({ url: "https://example.test/start" });
  const second = await service.fetchPage({ url: "https://example.test/start" });
  assert.equal(first.cached, false);
  assert.equal(second.cached, true);
  assert.equal(calls.length, 1);
  assert.match(first.text, /alpha text/);

  const search = await service.search({ query: "current fact", depth: "deep" });
  const cachedSearch = await service.search({
    query: "current fact",
    depth: "deep",
  });
  assert.equal(search.backend, "xai");
  assert.equal(search.results[0].url, "https://source.test/page");
  assert.equal(cachedSearch.cached, true);
  assert.equal(xaiCalls, 1);

  const crawl = await service.crawl({
    url: "https://example.test/start",
    max_pages: 4,
    max_depth: 2,
  });
  assert.deepEqual(
    crawl.pages.map((page) => page.url),
    ["https://example.test/start", "https://example.test/next"],
  );
  assert.equal(calls.includes("https://other.test/out"), false);
  assert(service.snapshot().cache.usedBytes > 0);
  service.close();
});

test("web fetch rejects redirects into private networks", async () => {
  const service = new InternetService({
    lookup: publicLookup,
    fetchImpl: async () =>
      new Response("", {
        status: 302,
        headers: { Location: "http://169.254.169.254/latest/meta-data" },
      }),
    settings: {
      cacheBytes: 1024 * 1024,
      cacheTtlMs: 60_000,
      concurrency: 1,
      queueLimit: 1,
      timeoutMs: 5_000,
      maxDownloadBytes: 64 * 1024,
      maxOutputChars: 32_000,
    },
  });
  await assert.rejects(
    () => service.fetchPage({ url: "https://example.test/redirect" }),
    /Private/,
  );
  service.close();
});

test("web fetch blocks direct and redirected TradingView extraction", async () => {
  let calls = 0;
  const service = new InternetService({
    lookup: publicLookup,
    fetchImpl: async () => {
      calls += 1;
      return new Response("", {
        status: 302,
        headers: { Location: "https://www.tradingview.com./chart/" },
      });
    },
    settings: {
      cacheBytes: 1024 * 1024,
      cacheTtlMs: 60_000,
      concurrency: 1,
      queueLimit: 1,
      timeoutMs: 5_000,
      maxDownloadBytes: 64 * 1024,
      maxOutputChars: 32_000,
    },
  });
  await assert.rejects(
    () => service.fetchPage({ url: "https://tradingview.com/chart/" }),
    { code: "alta_web_site_policy" },
  );
  assert.equal(calls, 0);
  await assert.rejects(
    () =>
      service.request("https://www.tradingview.com./chart/", {
        trustedOrigin: "https://www.tradingview.com.",
      }),
    { code: "alta_web_site_policy" },
  );
  assert.equal(calls, 0);
  await assert.rejects(
    () => service.fetchPage({ url: "https://example.test/redirect" }),
    { code: "alta_web_site_policy" },
  );
  assert.equal(calls, 1);
  service.close();
});

test("reader final URLs cannot bypass TradingView display-only policy", async () => {
  for (const reader of ["reader", "auto"]) {
    let calls = 0;
    const service = new InternetService({
      lookup: publicLookup,
      fetchImpl: async (url) => {
        calls += 1;
        if (new URL(url).hostname === "r.jina.ai")
          return new Response(
            '---\ntitle: "Redirected"\nurl: "https://www.tradingview.com./chart/"\n---\nTradingView extracted content',
            { headers: { "Content-Type": "text/plain" } },
          );
        return new Response("<html><body>enable javascript</body></html>", {
          headers: { "Content-Type": "text/html" },
        });
      },
      settings: {
        cacheBytes: 1024 * 1024,
        cacheTtlMs: 60_000,
        concurrency: 1,
        queueLimit: 1,
        timeoutMs: 5_000,
        maxDownloadBytes: 64 * 1024,
        maxOutputChars: 32_000,
        readerEnabled: true,
        readerMinimumChars: 500,
      },
    });
    await assert.rejects(
      () =>
        service.fetchPage({
          url: "https://example.test/reader-redirect",
          reader,
        }),
      { code: "alta_web_site_policy" },
    );
    assert.equal(calls, reader === "reader" ? 1 : 2);
    service.close();
  }
});

test("every public reader tool enforces TradingView display-only policy", async () => {
  let fetchCalls = 0;
  const target = "https://www.tradingview.com./chart/";
  const service = new InternetService({
    lookup: publicLookup,
    fetchImpl: async () => {
      fetchCalls += 1;
      throw new Error("TradingView must be rejected before HTTP");
    },
    settings: {
      cacheBytes: 1024 * 1024,
      cacheTtlMs: 60_000,
      concurrency: 1,
      queueLimit: 1,
      timeoutMs: 5_000,
      maxDownloadBytes: 64 * 1024,
      maxOutputChars: 32_000,
      readerEnabled: true,
      readerMinimumChars: 500,
    },
  });
  service.search = async () => ({
    backend: "test",
    results: [{ url: target, title: "Indexed", snippets: [] }],
  });
  let id = 40;
  const call = (name, args) =>
    handleMcpMessage(service, {
      jsonrpc: "2.0",
      id: (id += 1),
      method: "tools/call",
      params: { name, arguments: args },
    });
  for (const [name, args] of [
    ["alta_web_crawl", { url: target }],
    ["alta_web_sitemap", { url: target }],
    ["alta_web_feed", { url: target }],
    ["alta_web_archive", { url: target }],
    ["alta_social_read", { url: target }],
  ]) {
    const rejected = await call(name, args);
    assert.deepEqual(rejected.result.structuredContent.error, {
      code: "alta_web_site_policy",
      message:
        "TradingView permits display-only access; use alta_tradingview_navigate and open the returned page manually",
    });
  }

  const batch = await call("alta_web_batch_fetch", { urls: [target] });
  assert.equal(batch.result.structuredContent.failures, 1);
  assert.match(batch.result.structuredContent.pages[0].error, /display-only/);
  const research = await call("alta_web_research", {
    queries: ["indexed TradingView result"],
    max_pages: 1,
  });
  assert.equal(research.result.structuredContent.partial, true);
  assert.match(
    research.result.structuredContent.failures[0].error,
    /display-only/,
  );
  assert.equal(fetchCalls, 0);
  service.close();
});

test("Piped endpoint configuration keeps three credential-free HTTPS URLs", () => {
  const defaults = new InternetService({ env: {} });
  assert.deepEqual(defaults.pipedUrls, ["https://api.piped.private.coffee/"]);
  defaults.close();

  const configured = new InternetService({
    env: {
      ALTA_PIPED_URLS:
        "http://insecure.test,https://user@credential.test,invalid,https://one.test,https://two.test/base,https://three.test,https://four.test",
    },
  });
  assert.deepEqual(configured.pipedUrls, [
    "https://one.test/",
    "https://two.test/base",
    "https://three.test/",
  ]);
  configured.close();
});

test("MCP surface exposes every bounded internet tool and returns structured results", async () => {
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
  const service = {
    search: async (args) => ({
      backend: "test",
      query: args.query,
      results: [],
    }),
    fetchPage: async (args) => ({ url: args.url, text: "page" }),
    crawl: async (args) => ({ start_url: args.url, pages: [] }),
  };
  const discovery = await handleMcpMessage(service, {
    jsonrpc: "2.0",
    id: 1,
    method: "server/discover",
  });
  assert.equal(discovery.result.supportedVersions[0], "2026-07-28");

  const list = await handleMcpMessage(service, {
    jsonrpc: "2.0",
    id: 2,
    method: "tools/list",
  });
  assert.deepEqual(
    list.result.tools.map((tool) => tool.name),
    internetToolNames(),
  );
  assert.deepEqual(
    list.result.tools.find((tool) => tool.name === "alta_tradingview_navigate")
      .annotations,
    {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
  );

  const initialized = await handleMcpMessage(service, {
    jsonrpc: "2.0",
    id: 20,
    method: "initialize",
    params: { protocolVersion: "2026-07-28" },
  });
  assert.match(initialized.result.instructions, /academic search/);
  assert.match(initialized.result.instructions, /social search/);
  assert.match(initialized.result.instructions, /finance data/);
  assert.match(initialized.result.instructions, /TradingView navigation/);
  assert.match(initialized.result.instructions, /never pass its URLs to fetch/);
  assert.match(initialized.result.instructions, /file read/);

  const call = await handleMcpMessage(service, {
    jsonrpc: "2.0",
    id: 3,
    method: "tools/call",
    params: { name: "alta_web_search", arguments: { query: "test" } },
  });
  assert.equal(call.result.structuredContent.query, "test");
  assert.match(call.result.content[0].text, /"backend": "test"/);

  const navigation = await handleMcpMessage(service, {
    jsonrpc: "2.0",
    id: 30,
    method: "tools/call",
    params: {
      name: "alta_tradingview_navigate",
      arguments: { action: "chart", symbol: "NASDAQ:AAPL", interval: "D" },
    },
  });
  assert.deepEqual(navigation.result.structuredContent, {
    source: "tradingview",
    mode: "display_only_navigation",
    action: "chart",
    symbol: "NASDAQ:AAPL",
    url: "https://www.tradingview.com/chart/?symbol=NASDAQ%3AAAPL&interval=D",
    machine_data_tools: ["alta_finance_data", "alta_news_search"],
    notice:
      "Open this page for human-readable display; do not send it to ALTA fetch, batch-fetch, crawl, research, sitemap, feed, social-read, or archive tools.",
  });
  const invalidNavigation = await handleMcpMessage(service, {
    jsonrpc: "2.0",
    id: 31,
    method: "tools/call",
    params: {
      name: "alta_tradingview_navigate",
      arguments: { action: "chart", symbol: "https://example.test" },
    },
  });
  assert.deepEqual(invalidNavigation.result.structuredContent.error, {
    code: "alta_tradingview_invalid_argument",
    message: "symbol must use a bounded EXCHANGE:TICKER identifier",
  });
  assert.equal(invalidNavigation.result.isError, true);

  service.fetchPage = async () => ({ text: "x".repeat(50_000) });
  const bounded = await handleMcpMessage(service, {
    jsonrpc: "2.0",
    id: 4,
    method: "tools/call",
    params: {
      name: "alta_web_fetch",
      arguments: { url: "https://example.test" },
    },
  });
  assert.equal(bounded.result.structuredContent.truncated, true);
  assert(Buffer.byteLength(bounded.result.content[0].text) <= 9_000);
  assert.match(bounded.result.content[0].text, /ALTA truncated this result/);

  service.fetchPage = async () => ({ text: "𒀀".repeat(20_000) });
  const tokenDense = await handleMcpMessage(service, {
    jsonrpc: "2.0",
    id: 5,
    method: "tools/call",
    params: {
      name: "alta_web_fetch",
      arguments: { url: "https://example.test/dense" },
    },
  });
  assert.equal(tokenDense.result.structuredContent.truncated, true);
  assert(Buffer.byteLength(tokenDense.result.content[0].text) <= 9_000);
  assert(tokenDense.result.structuredContent.original_bytes > 9_000);

  for (const [id, message, code] of [
    [6, "\u0001".repeat(2_000), "\u0001".repeat(200)],
    [7, "𒀀".repeat(2_000), "alta_unicode_error"],
  ]) {
    service.search = async () => {
      const error = new Error(message);
      error.code = code;
      throw error;
    };
    const failed = await handleMcpMessage(service, {
      jsonrpc: "2.0",
      id,
      method: "tools/call",
      params: { name: "alta_web_search", arguments: { query: "failure" } },
    });
    assert.equal(failed.result.isError, true);
    assert.equal(
      failed.result.content[0].text,
      failed.result.structuredContent.error.message,
    );
    assert.equal(
      failed.result.structuredContent.error.code,
      id === 6 ? "alta_web_error" : code,
    );
    if (id === 7)
      assert.equal(
        failed.result.structuredContent.error.message.startsWith("𒀀"),
        true,
      );
    assert(Buffer.byteLength(JSON.stringify(failed.result)) <= 900);
    assert(Buffer.byteLength(JSON.stringify(failed)) <= 1_000);
  }

  for (const [id, code] of [
    [8, 23],
    [9, "alta_source_timeout"],
  ]) {
    service.search = async () => {
      const error = new Error("bounded failure");
      error.code = code;
      throw error;
    };
    const compatible = await handleMcpMessage(service, {
      jsonrpc: "2.0",
      id,
      method: "tools/call",
      params: { name: "alta_web_search", arguments: { query: "failure" } },
    });
    assert.equal(compatible.result.structuredContent.error.code, code);
  }
});
