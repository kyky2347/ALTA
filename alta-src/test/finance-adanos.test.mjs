import test from "node:test";
import assert from "node:assert/strict";
import { InternetService } from "../internet/service.mjs";
import { executeInternetTool } from "../internet/plugins/registry.mjs";
import { loadResourceCredentials } from "../resource-credentials.mjs";

const KEY = "adanos_synthetic_fixture_1234567890";
const request = {
  source: "adanos",
  dataset: "reddit_stocks",
  symbol: "EXM",
  from_date: "2026-10-01",
  to_date: "2026-10-02",
};

function service(t, fetchImpl, key = KEY) {
  const value = new InternetService({
    env: {},
    adanosKey: key,
    fetchImpl,
    lookup: async () => [{ address: "93.184.216.34", family: 4 }],
  });
  t.after(() => value.close());
  return value;
}

test("Adanos credential loads through the external operator boundary", () => {
  const value = loadResourceCredentials({ ADANOS_API_KEY: KEY }, [
    "ADANOS_API_KEY",
  ]);
  assert.equal(value.values.ADANOS_API_KEY, KEY);
  assert.equal(value.sources.ADANOS_API_KEY, "environment (ADANOS_API_KEY)");
});

for (const [dataset, suffix] of [
  ["reddit_stocks", "reddit/stocks/v1/stock/EXM"],
  ["reddit_crypto", "reddit/crypto/v1/token/EXM"],
  ["x_stocks", "x/stocks/v1/stock/EXM"],
  ["news_stocks", "news/stocks/v1/stock/EXM"],
  ["polymarket_stocks", "polymarket/stocks/v1/stock/EXM"],
]) {
  test(`Adanos ${dataset} preserves response and observation provenance`, async (t) => {
    const value = service(t, async (url, options) => {
      assert.equal(
        url.href,
        `https://api.adanos.org/${suffix}?from=2026-10-01&to=2026-10-02`,
      );
      assert.equal(options.headers["X-API-Key"], KEY);
      return Response.json({ sentiment_score: 0.3, mentions: 12 });
    });
    const result = await executeInternetTool(
      value,
      "alta_finance_data",
      { ...request, dataset },
      {},
    );
    assert.deepEqual(result.data, { sentiment_score: 0.3, mentions: 12 });
    assert.equal(result.dataset, dataset);
    assert.equal(result.provenance.authentication, "api_key");
    assert.equal(Number.isNaN(Date.parse(result.observed_at)), false);
    assert.match(result.interpretation, /not point-in-time/);
    assert.equal(JSON.stringify(result).includes(KEY), false);
  });
}

for (const args of [
  { dataset: "news_crypto" },
  { from_date: "2026-02-30" },
  { from_date: "2026-10-03" },
  { symbol: "../health" },
  { to_date: undefined },
  { from_date: undefined },
]) {
  test(`Adanos refuses invalid input ${JSON.stringify(args)}`, async (t) => {
    const value = service(t, () => assert.fail("must not fetch"));
    await assert.rejects(
      executeInternetTool(
        value,
        "alta_finance_data",
        { ...request, ...args },
        {},
      ),
      (error) => {
        assert.equal(error.status, 400);
        assert.match(error.code, /^alta_finance_invalid_(argument|date)$/);
        return true;
      },
    );
  });
}

test("Adanos missing credential refuses without fetching", async (t) => {
  const value = service(t, () => assert.fail("must not fetch"), null);
  await assert.rejects(
    executeInternetTool(value, "alta_finance_data", request, {}),
    { code: "alta_finance_adanos_credential_missing" },
  );
});

for (const status of [401, 403, 429, 500]) {
  test(`Adanos HTTP ${status} stays an explicit safe error, without retries`, async (t) => {
    let calls = 0;
    const value = service(t, () => {
      calls++;
      return new Response(KEY, { status });
    });
    await assert.rejects(
      executeInternetTool(value, "alta_finance_data", request, {}),
      (error) => {
        assert.equal(error.status, status);
        assert.equal(error.message.includes(KEY), false);
        return true;
      },
    );
    assert.equal(calls, 1);
  });
}

test("Adanos rejects malformed JSON rather than manufacturing evidence", async (t) => {
  const value = service(t, () => new Response("not-json"));
  await assert.rejects(
    executeInternetTool(value, "alta_finance_data", request, {}),
    { code: "alta_finance_adanos_unavailable" },
  );
});
