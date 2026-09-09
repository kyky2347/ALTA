import assert from "node:assert/strict";
import test from "node:test";
import { ApiError, getJson } from "../src/lib/api.ts";
import { validConsolePayload } from "../src/lib/response-contract.ts";
import {
  previewCapital,
  previewControl,
  previewCredentials,
  previewEvents,
  previewRuntime,
  previewStatus,
} from "../src/lib/preview.ts";

test("current preview fixtures satisfy the same API read contracts", () => {
  for (const [path, data] of [
    ["/control/state", previewControl],
    ["/control/capital", previewCapital],
    ["/control/credentials", previewCredentials],
    ["/proxy/api/v1/events", { events: previewEvents }],
    ["/proxy/api/v1/system/runtime", previewRuntime],
    ["/proxy/api/v1/mvp/status?limit=100", previewStatus],
  ])
    assert.equal(validConsolePayload(path, data), true, path);
});

test("malformed successful responses never become usable snapshots", async (context) => {
  for (const body of [
    "not-json",
    "null",
    "{}",
    '{"data":null}',
    '{"data":{"eventCursor":1}}',
  ]) {
    context.mock.method(globalThis, "fetch", async () => new Response(body));
    await assert.rejects(getJson("/proxy/api/v1/mvp/status"), {
      name: "ApiError",
      code: "invalid_response",
      retriable: true,
    });
    context.mock.restoreAll();
  }
});

test("invalid rows and unsafe capital environments are rejected", () => {
  assert.equal(
    validConsolePayload("/proxy/api/v1/mvp/status", {
      ...previewStatus,
      opportunities: [null],
    }),
    false,
  );
  assert.equal(
    validConsolePayload("/proxy/api/v1/mvp/status", {
      ...previewStatus,
      ranks: [{ id: "r", book: null }],
    }),
    false,
  );
  assert.equal(
    validConsolePayload("/control/capital", {
      ...previewCapital,
      environment: "LIVE",
    }),
    false,
  );
  assert.equal(
    validConsolePayload("/control/state", { ...previewControl, runtime: null }),
    false,
  );
});

test("non-JSON HTTP failure preserves retry status without leaking its body", async (context) => {
  context.mock.method(
    globalThis,
    "fetch",
    async () => new Response("private-upstream-diagnostic", { status: 503 }),
  );
  await assert.rejects(
    getJson("/control/state"),
    (error) =>
      error instanceof ApiError &&
      error.status === 503 &&
      error.retriable &&
      !error.message.includes("private-upstream"),
  );
});

test("timeout during JSON body read remains a timeout, not malformed success", async (context) => {
  context.mock.method(
    globalThis,
    "fetch",
    async (_url, { signal }) =>
      new Response(
        new ReadableStream({
          start(controller) {
            signal.addEventListener("abort", () =>
              controller.error(signal.reason),
            );
          },
        }),
      ),
  );
  await assert.rejects(getJson("/control/state", { timeoutMs: 10 }), {
    code: "request_timeout",
  });
});
