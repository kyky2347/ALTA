import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  discoverProviderModels,
  fallbackModels,
  fetchJsonWithRetry,
  loadCredentials,
  providerModelCapabilities,
  redact,
} from "../providers.mjs";

test("provider discovery honors Retry-After without a hot retry loop", async () => {
  let calls = 0;
  const delays = [];
  const value = await fetchJsonWithRetry(
    "https://api.example.test/models",
    {},
    {
      attempts: 2,
      fetchImpl: async () => {
        calls += 1;
        return calls === 1
          ? new Response("busy", {
              status: 503,
              headers: { "Retry-After": "2" },
            })
          : Response.json({ data: [{ id: "ready" }] });
      },
      sleepImpl: async (delay) => delays.push(delay),
    },
  );
  assert.deepEqual(
    { calls, delays, value },
    {
      calls: 2,
      delays: [2_000],
      value: { data: [{ id: "ready" }] },
    },
  );
});

test("credential loader reads external RTF files without exposing values", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "alta-keys-"));
  const keys = path.join(root, "llm");
  fs.mkdirSync(keys, { recursive: true, mode: 0o700 });
  fs.writeFileSync(
    path.join(keys, "DeepSeek API.rtf"),
    String.raw`{\rtf1 key ${"sk-" + "deepseek_test_12345678901234567890"}}`,
    { mode: 0o600 },
  );
  fs.writeFileSync(
    path.join(keys, "Grok API.rtf"),
    String.raw`{\rtf1 key xai-grok_test_123456789012345678901234}`,
    { mode: 0o600 },
  );
  fs.writeFileSync(
    path.join(keys, "Kimi API.rtf"),
    String.raw`{\rtf1 key ${"sk-" + "kimi_test_1234567890123456789012"}}`,
    { mode: 0o600 },
  );
  const { credentials, sources } = loadCredentials({
    ALTA_CREDENTIALS_DIR: root,
  });
  assert.match(credentials.deepseek, /^sk-/);
  assert.match(credentials.xai, /^xai-/);
  assert.match(credentials.kimi, /^sk-/);
  assert.match(sources.deepseek, /external credential file/);
  assert.equal(
    redact(`Bearer ${credentials.deepseek}`, Object.values(credentials)),
    "Bearer [REDACTED]",
  );
  fs.rmSync(root, { recursive: true, force: true });
});

test("credential loader rejects a relative external directory", () => {
  assert.throws(
    () => loadCredentials({ ALTA_CREDENTIALS_DIR: "relative/credentials" }),
    /must be an absolute path/,
  );
});

test(
  "credential loader rejects group-readable external files",
  { skip: process.platform === "win32" },
  () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "alta-keys-mode-"));
    const keys = path.join(root, "llm");
    fs.mkdirSync(keys, { mode: 0o700 });
    fs.writeFileSync(
      path.join(keys, "DeepSeek API.rtf"),
      String.raw`{\rtf1 key ${"sk-" + "deepseek_test_12345678901234567890"}}`,
      { mode: 0o640 },
    );
    assert.throws(
      () => loadCredentials({ ALTA_CREDENTIALS_DIR: root }),
      /owner-only regular files/,
    );
    fs.rmSync(root, { recursive: true, force: true });
  },
);

test("provider discovery normalizes vendor-specific model metadata", async () => {
  const jsonResponse = (value) =>
    new Response(JSON.stringify(value), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  const deepseek = await discoverProviderModels("deepseek", "sk-test", {
    fetchImpl: async () =>
      jsonResponse({
        data: [
          { id: "deepseek-v4-pro" },
          { id: "deepseek-v4-flash-vision-exp" },
        ],
      }),
  });
  assert.deepEqual(
    deepseek.map((model) => ({
      id: model.id,
      context_window: model.context_window,
      input_modalities: model.input_modalities,
      reasoning: model.reasoning,
    })),
    [
      {
        id: "deepseek-v4-pro",
        context_window: 1_000_000,
        input_modalities: ["text"],
        reasoning: true,
      },
      {
        id: "deepseek-v4-flash-vision-exp",
        context_window: 1_000_000,
        input_modalities: ["text", "image"],
        reasoning: true,
      },
    ],
  );

  const xai = await discoverProviderModels("xai", "xai-test", {
    fetchImpl: async () =>
      jsonResponse({
        models: [
          {
            id: "grok-4.6",
            input_modalities: ["text", "image", "audio"],
          },
          { id: "grok-4.20-0309-non-reasoning" },
        ],
      }),
  });
  assert.equal(xai[0].context_window, 500_000);
  assert.deepEqual(xai[0].input_modalities, ["text", "image"]);
  assert.equal(xai[0].image, true);
  assert.equal(xai[0].audio, false);
  assert.equal(xai[1].reasoning, false);

  assert.deepEqual(providerModelCapabilities("deepseek", "deepseek-v4-pro"), {
    inputModalities: ["text"],
    video: false,
  });
  assert.deepEqual(
    providerModelCapabilities("deepseek", "deepseek-v4-flash-vision-exp"),
    { inputModalities: ["text", "image"], video: false },
  );
  assert.deepEqual(
    providerModelCapabilities("kimi", "future-kimi", {
      input_modalities: ["text", "audio"],
    }),
    { inputModalities: ["text"], video: false },
  );
  assert.deepEqual(
    fallbackModels("deepseek").map((model) => ({
      id: model.id,
      context_window: model.context_window,
      input_modalities: model.input_modalities,
    })),
    [
      {
        id: "deepseek-v4-pro",
        context_window: 1_000_000,
        input_modalities: ["text"],
      },
      {
        id: "deepseek-v4-flash",
        context_window: 1_000_000,
        input_modalities: ["text"],
      },
      {
        id: "deepseek-v4-flash-vision-exp",
        context_window: 1_000_000,
        input_modalities: ["text", "image"],
      },
    ],
  );
  assert.deepEqual(
    fallbackModels("kimi").map((model) => ({
      id: model.id,
      input_modalities: model.input_modalities,
      video: model.video,
    })),
    [
      { id: "kimi-k3", input_modalities: ["text", "image"], video: true },
      {
        id: "kimi-k2.7-code",
        input_modalities: ["text", "image"],
        video: true,
      },
      {
        id: "kimi-k2.7-code-highspeed",
        input_modalities: ["text", "image"],
        video: true,
      },
      {
        id: "kimi-k2.6",
        input_modalities: ["text", "image"],
        video: true,
      },
    ],
  );
});
