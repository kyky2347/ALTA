import assert from "node:assert/strict";
import test from "node:test";
import { readConsoleUpstream } from "../console-upstream.mjs";

const target = "http://127.0.0.1:1/api/v1/system/summary";

test("console upstream bounds advertised and streamed bodies and releases them", async () => {
  for (const advertised of [true, false]) {
    let cancelled = false;
    const response = new Response(
      new ReadableStream({
        pull(controller) {
          controller.enqueue(new Uint8Array(9));
        },
        cancel() {
          cancelled = true;
        },
      }),
      { headers: advertised ? { "Content-Length": "9" } : {} },
    );
    await assert.rejects(
      readConsoleUpstream(target, {
        maximumBytes: 8,
        fetchImpl: async () => response,
      }),
      { code: "upstream_response_too_large", statusCode: 502 },
    );
    assert.equal(cancelled, true);
    assert.equal(response.body.locked, false);
  }
});

test("console upstream preserves response status and bounded body", async () => {
  const response = await readConsoleUpstream(target, {
    fetchImpl: async () => new Response('{"error":{}}', { status: 503 }),
  });
  assert.equal(response.status, 503);
  assert.equal(response.body.toString(), '{"error":{}}');
});

test("console upstream sanitizes transport errors", async () => {
  await assert.rejects(
    readConsoleUpstream(target, {
      fetchImpl: async () => {
        throw new Error("private-driver-diagnostic");
      },
    }),
    (error) =>
      error.code === "upstream_unavailable" &&
      !error.message.includes("private-driver"),
  );
});

test("console upstream does not fetch after its browser has disconnected", async () => {
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(
    readConsoleUpstream(target, {
      signal: controller.signal,
      fetchImpl: () => assert.fail("must not fetch"),
    }),
    { code: "upstream_cancelled" },
  );
});

test("console upstream timeout aborts an unfinished body", async () => {
  let cancelled = false;
  // Keep the synthetic transport alive like a real socket; production timeout
  // timers themselves must not keep an otherwise stopped process running.
  const keepAlive = setTimeout(() => {}, 1000);
  try {
    await assert.rejects(
      readConsoleUpstream(target, {
        timeoutMs: 10,
        fetchImpl: async (_target, { signal }) =>
          new Response(
            new ReadableStream({
              start(controller) {
                signal.addEventListener("abort", () => {
                  cancelled = true;
                  controller.error(signal.reason);
                });
              },
            }),
          ),
      }),
      { code: "upstream_timeout", statusCode: 504 },
    );
    assert.equal(cancelled, true);
  } finally {
    clearTimeout(keepAlive);
  }
});
