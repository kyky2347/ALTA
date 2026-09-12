import test from "node:test";
import assert from "node:assert/strict";
import { setTimeout as delay } from "node:timers/promises";
import { BackendHealth } from "../internet/backend-health.mjs";
import { executeInternetTool } from "../internet/plugins/registry.mjs";

function service(observed) {
  return {
    backendHealth: new BackendHealth(),
    recordTool: () => {},
    readText: async (request) => {
      const url = new URL(request.url);
      observed.push({
        host: url.hostname,
        path: url.pathname,
        query: Object.fromEntries(url.searchParams.entries()),
        cache: request.cache_namespace,
        attempts: request.attempts,
      });
      if (url.hostname === "www.bankofcanada.ca")
        return {
          text: JSON.stringify({
            observations: Array.from({ length: 30 }, (_, index) => ({
              d: `2026-07-${String(index + 1).padStart(2, "0")}`,
              FXUSDCAD: { v: String(1.3 + index / 100) },
            })),
          }),
        };
      if (url.hostname === "ec.europa.eu")
        return {
          text: JSON.stringify({
            class: "dataset",
            label: "Gross domestic product",
            updated: "2026-08-19T12:00:00Z",
            id: ["freq", "unit", "geo", "time"],
            size: [1, 1, 1, 12],
            dimension: {
              freq: { category: { index: ["A"] } },
              unit: { category: { index: { CLV10_MEUR: 0 } } },
              geo: { category: { index: ["DE"] } },
              time: {
                category: {
                  index: Array.from({ length: 12 }, (_, index) =>
                    String(2015 + index),
                  ),
                },
              },
            },
            value: { 0: 100, 2: 102, 5: null, 7: 107, 11: 111 },
            status: { 0: "p", 2: "", 7: "e", 11: "p" },
          }),
        };
      if (
        url.hostname === "api.kraken.com" &&
        url.pathname.endsWith("/PostTrade")
      )
        return {
          text: JSON.stringify({
            error: [],
            result: {
              trades: Array.from({ length: 12 }, (_, index) => ({
                trade_id: `trade-${index}`,
                symbol: "BTC/USD",
                price: String(60_000 + index),
                quantity: "0.2",
                trade_ts: `2026-08-19T12:00:${String(index).padStart(2, "0")}Z`,
                publication_ts: `2026-08-19T12:01:${String(index).padStart(2, "0")}Z`,
                trade_venue: "XKRA",
              })),
            },
          }),
        };
      if (url.hostname === "api.kraken.com")
        return {
          text: JSON.stringify({
            error: [],
            result: {
              symbol: "BTC/USD",
              description: "Bitcoin / US Dollars",
              bids: Array.from({ length: 10 }, (_, index) => ({
                side: "BUY",
                price: String(60_000 - index),
                qty: "2.5",
                count: index + 1,
                publication_ts: "2026-08-19T12:00:00Z",
              })),
              asks: Array.from({ length: 10 }, (_, index) => ({
                side: "SELL",
                price: String(60_001 + index),
                qty: "1.5",
                count: index + 1,
                publication_ts: "2026-08-19T12:00:01Z",
              })),
            },
          }),
        };
      throw new Error(`unexpected global finance source: ${url.hostname}`);
    },
  };
}

async function allPages(observed, args) {
  const pages = [];
  const records = [];
  let cursor = 0;
  let snapshot = "";
  do {
    const result = await executeInternetTool(
      service(observed),
      "alta_finance_data",
      { ...args, cursor, ...(snapshot ? { snapshot } : {}) },
      {},
    );
    assert(Buffer.byteLength(JSON.stringify(result)) <= 900);
    if (snapshot) assert.equal(result.snapshot, snapshot);
    else snapshot = result.snapshot;
    if (result.next_cursor !== null)
      assert(result.next_cursor > cursor, "finance cursor must advance");
    pages.push(result);
    records.push(...result.records);
    cursor = result.next_cursor;
    assert(pages.length < 100, "finance pagination did not terminate");
  } while (cursor !== null);
  return { pages, records, snapshot };
}

test("global finance adapters are bounded, login-free, and source-isolated", async () => {
  const observed = [];
  const boc = await allPages(observed, {
    source: "boc",
    series_id: "FXUSDCAD",
    from_date: "2026-07-01",
    to_date: "2026-07-30",
    max_records: 30,
  });
  const eurostat = await allPages(observed, {
    source: "eurostat",
    dataset_code: "nama_10_gdp",
    filters: ["geo=DE", "unit=CLV10_MEUR"],
    from_period: "2025",
    to_period: "2026",
    max_records: 2,
  });
  const orderBook = await allPages(observed, {
    source: "kraken",
    symbol: "BTC/USD",
    market_mode: "order_book",
  });
  const trades = await allPages(observed, {
    source: "kraken",
    symbol: "BTC/USD",
    market_mode: "trades",
  });

  for (const result of [boc, eurostat, orderBook, trades])
    assert(result.pages.length > 1);
  assert.equal(new Set(boc.records.map(({ date }) => date)).size, 30);
  assert.deepEqual(
    eurostat.records.map(({ dimensions, value, status }) => ({
      time: dimensions.at(-1),
      value,
      status,
    })),
    [
      { time: "time=2015", value: 100, status: "p" },
      { time: "time=2017", value: 102, status: "" },
      { time: "time=2022", value: 107, status: "e" },
      { time: "time=2026", value: 111, status: "p" },
    ],
  );
  assert.deepEqual(
    new Set(orderBook.records.map(({ price }) => price)).size,
    20,
  );
  assert.equal(
    new Set(trades.records.map(({ trade_id }) => trade_id)).size,
    12,
  );
  const requests = new Map(observed.map((request) => [request.cache, request]));
  assert.deepEqual(
    [...requests.values()].map(({ host, cache, attempts }) => ({
      host,
      cache,
      attempts,
    })),
    [
      {
        host: "www.bankofcanada.ca",
        cache: "finance-boc-valet",
        attempts: 2,
      },
      {
        host: "ec.europa.eu",
        cache: "finance-eurostat-jsonstat",
        attempts: 1,
      },
      {
        host: "api.kraken.com",
        cache: "finance-kraken-order_book",
        attempts: 2,
      },
      {
        host: "api.kraken.com",
        cache: "finance-kraken-trades",
        attempts: 2,
      },
    ],
  );
  assert.deepEqual(requests.get("finance-eurostat-jsonstat").query, {
    format: "JSON",
    lang: "EN",
    sinceTimePeriod: "2025",
    untilTimePeriod: "2026",
    geo: "DE",
    unit: "CLV10_MEUR",
  });
});

test("finance snapshots reject moving market data between pages", async () => {
  let version = 0;
  const dense = "\0".repeat(80);
  const movingService = () => ({
    backendHealth: new BackendHealth(),
    recordTool: () => {},
    readText: async () => ({
      text: JSON.stringify({
        error: [],
        result: {
          trades: [
            {
              trade_id: `${version}${dense}`,
              symbol: dense,
              price: dense,
              quantity: dense,
              trade_ts: dense,
              publication_ts: dense,
              trade_venue: dense,
            },
          ],
        },
      }),
    }),
  });
  const first = await executeInternetTool(
    movingService(),
    "alta_finance_data",
    { source: "kraken", symbol: "BTC/USD", market_mode: "trades" },
    {},
  );
  assert(first.next_cursor > 0);
  assert.match(first.snapshot, /^[A-Za-z0-9_-]{16}$/);
  version = 1;
  await assert.rejects(
    () =>
      executeInternetTool(
        movingService(),
        "alta_finance_data",
        {
          source: "kraken",
          symbol: "BTC/USD",
          market_mode: "trades",
          cursor: first.next_cursor,
          snapshot: first.snapshot,
        },
        {},
      ),
    { code: "alta_finance_snapshot_changed" },
  );
});

test("finance adapters propagate cancellation, pacing, and circuit recovery", async () => {
  const controller = new AbortController();
  const cancellationHealth = new BackendHealth();
  let sourceSignal;
  const cancelled = executeInternetTool(
    {
      backendHealth: cancellationHealth,
      recordTool: () => {},
      readText: async (_request, { signal }) => {
        sourceSignal = signal;
        return new Promise((_, reject) => {
          if (signal.aborted) reject(signal.reason);
          else
            signal.addEventListener("abort", () => reject(signal.reason), {
              once: true,
            });
        });
      },
    },
    "alta_finance_data",
    { source: "boc", series_id: "FXUSDCAD" },
    { signal: controller.signal },
  );
  controller.abort(new Error("caller cancelled"));
  await assert.rejects(() => cancelled, /caller cancelled/);
  assert.equal(sourceSignal.aborted, true);
  assert.deepEqual(cancellationHealth.snapshot(), {});

  let attempts = 0;
  let now = 0;
  const marketHealth = new BackendHealth({
    failureThreshold: 1,
    baseCooldownMs: 400,
    maxCooldownMs: 400,
    now: () => now,
  });
  const marketService = {
    backendHealth: marketHealth,
    recordTool: () => {},
    readText: async () => {
      attempts += 1;
      if (attempts === 1)
        throw Object.assign(new Error("temporary market outage"), {
          status: 503,
        });
      return {
        text: JSON.stringify({
          error: [],
          result: { symbol: "BTC/USD", bids: [], asks: [] },
        }),
      };
    },
  };
  const request = { source: "kraken", symbol: "BTC/USD" };
  await assert.rejects(
    () => executeInternetTool(marketService, "alta_finance_data", request, {}),
    /temporary market outage/,
  );
  assert.equal(marketHealth.snapshot()["finance:kraken"].state, "open");
  await assert.rejects(
    () => executeInternetTool(marketService, "alta_finance_data", request, {}),
    { code: "alta_source_circuit_open" },
  );
  await delay(260);
  await assert.rejects(
    () => executeInternetTool(marketService, "alta_finance_data", request, {}),
    { code: "alta_source_circuit_open" },
  );
  await delay(260);
  now = 400;
  const recovered = await executeInternetTool(
    marketService,
    "alta_finance_data",
    request,
    {},
  );
  assert.equal(recovered.source, "kraken");
  assert.equal(marketHealth.snapshot()["finance:kraken"].state, "closed");
  assert.equal(attempts, 2);
});

test("global finance adapters reject unbounded or malformed requests", async () => {
  const context = service([]);
  await assert.rejects(
    () =>
      executeInternetTool(
        context,
        "alta_finance_data",
        { source: "eurostat", dataset_code: "nama_10_gdp" },
        {},
      ),
    { code: "alta_finance_invalid_argument" },
  );
  await assert.rejects(
    () =>
      executeInternetTool(
        context,
        "alta_finance_data",
        { source: "kraken", symbol: "BTC/USD?secret=x" },
        {},
      ),
    { code: "alta_finance_invalid_argument" },
  );
  await assert.rejects(
    () =>
      executeInternetTool(
        service([]),
        "alta_finance_data",
        { source: "boc", series_id: "FXUSDCAD", cursor: 1 },
        {},
      ),
    { code: "alta_finance_invalid_argument" },
  );
});
