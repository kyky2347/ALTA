import test from "node:test";
import assert from "node:assert/strict";
import { crawlSite } from "../internet/crawl.mjs";
import { InternetService } from "../internet/service.mjs";

function setup() {
  const fetched = [];
  const service = {
    fetchPage: async ({ url }) => {
      fetched.push(url);
      return {
        url,
        title: "Source",
        text: "source excerpt",
        cached: true,
        stale: true,
        metadata: { published_time: "2026-01-01" },
        links: url.endsWith("/home")
          ? [
              { url: "https://issuer.test/privacy", text: "Privacy" },
              {
                url: "https://issuer.test/investors/2026",
                text: "Investor earnings results",
              },
              {
                url: "https://other.test/earnings",
                text: "Investor earnings results",
              },
              { url: "https://issuer.test/2026-calendar", text: "2026" },
            ]
          : [],
      };
    },
  };
  const settings = {
    start: new URL("https://issuer.test/home"),
    pagesLimit: 2,
    depthLimit: 1,
    charsLimit: 4000,
    concurrency: 2,
  };
  return { service, fetched, settings };
}

test("direct-site research prioritizes relevant retrieved links within the same hard bounds", async () => {
  const { service, fetched, settings } = setup();
  const result = await crawlSite(service, {
    ...settings,
    query: "investor earnings 2026",
  });
  assert.deepEqual(fetched, [
    "https://issuer.test/home",
    "https://issuer.test/investors/2026",
  ]);
  assert.equal(result.attempt_count, 2);
  assert(result.character_count <= 4000);
  assert.equal(result.stale, true);
  assert.equal(result.pages[1].metadata.published_time, "2026-01-01");
  assert.equal(result.pages[1].stale, true);
});

test("unscoped crawling retains document order and depth zero never traverses", async () => {
  const { service, fetched, settings } = setup();
  await crawlSite(service, settings);
  assert.equal(fetched[1], "https://issuer.test/privacy");
  fetched.length = 0;
  await crawlSite(service, { ...settings, query: "earnings", depthLimit: 0 });
  assert.equal(fetched.length, 1);
});

test("date-only query does not boost calendar navigation; invalid input does no network I/O", async () => {
  const { service, fetched, settings } = setup();
  await crawlSite(service, { ...settings, query: "2026" });
  assert.equal(fetched[1], "https://issuer.test/privacy");
  let requests = 0;
  const runtime = new InternetService({
    fetchImpl: () => {
      requests++;
    },
  });
  try {
    await assert.rejects(
      runtime.crawl({ url: "https://issuer.test", query: "x".repeat(401) }),
      { code: "alta_web_invalid_query" },
    );
    assert.equal(requests, 0);
  } finally {
    runtime.close();
  }
});

test("cancelled direct-site research does not start another fetch", async () => {
  const { service, fetched, settings } = setup();
  await assert.rejects(
    crawlSite(service, settings, { signal: AbortSignal.abort() }),
  );
  assert.equal(fetched.length, 0);
});
