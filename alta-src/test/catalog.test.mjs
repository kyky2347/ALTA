import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  resolveProviderModels,
  writeCatalogs,
  writeConfig,
} from "../catalog.mjs";

const rootDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);

test("combined catalog and config expose every provider to nested agents", () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "alta-catalog-"));
  try {
    const catalogs = writeCatalogs(rootDir, stateDir, [
      {
        id: "deepseek-test",
        provider: "deepseek",
        context_window: 128_000,
        reasoning: true,
        image: false,
      },
      {
        id: "deepseek-v4-flash-vision-exp",
        provider: "deepseek",
        context_window: 1_000_000,
        reasoning: true,
        input_modalities: ["text", "image"],
        image: true,
      },
      {
        id: "grok-test",
        provider: "xai",
        context_window: 128_000,
        reasoning: true,
        input_modalities: ["text", "image", "audio"],
        image: true,
        audio: true,
      },
      {
        id: "kimi-test",
        provider: "kimi",
        context_window: 128_000,
        reasoning: true,
        input_modalities: ["text", "image"],
        image: true,
        video: true,
      },
    ]);
    const catalog = JSON.parse(fs.readFileSync(catalogs.combinedFile, "utf8"));
    const modelIds = new Set(catalog.models.map((model) => model.slug));
    assert(modelIds.has("gpt-5.6-sol"));
    assert(modelIds.has("deepseek-test"));
    assert(modelIds.has("deepseek-v4-flash-vision-exp"));
    assert(modelIds.has("grok-test"));
    assert(modelIds.has("kimi-test"));
    assert.deepEqual(
      Object.fromEntries(
        catalog.models
          .filter((model) =>
            ["deepseek-test", "grok-test", "kimi-test"].includes(model.slug),
          )
          .map((model) => [model.slug, model.default_reasoning_level]),
      ),
      {
        "deepseek-test": "low",
        "grok-test": "low",
        "kimi-test": "none",
      },
    );
    for (const model of catalog.models.filter((value) =>
      [
        "deepseek-test",
        "deepseek-v4-flash-vision-exp",
        "grok-test",
        "kimi-test",
      ].includes(value.slug),
    )) {
      assert.equal(model.include_skills_usage_instructions, false);
      assert.equal(model.include_plugin_usage_instructions, false);
      assert.equal(model.include_apps_usage_instructions, false);
      assert.match(
        model.model_messages.instructions_template,
        /Use only tools exposed in this session/,
      );
      assert.match(
        model.model_messages.instructions_template,
        /Never place, modify, or cancel orders/,
      );
      assert.ok(
        Buffer.byteLength(model.model_messages.instructions_template) < 1_500,
      );
    }
    assert.deepEqual(
      catalog.models
        .filter((model) => model.slug === "deepseek-v4-flash-vision-exp")
        .map((model) => ({
          input_modalities: model.input_modalities,
          supports_image_detail_original: model.supports_image_detail_original,
        })),
      [
        {
          input_modalities: ["text", "image"],
          supports_image_detail_original: true,
        },
      ],
    );
    assert.deepEqual(
      Object.fromEntries(
        catalog.models
          .filter((model) => ["grok-test", "kimi-test"].includes(model.slug))
          .map((model) => [model.slug, model.input_modalities]),
      ),
      {
        "grok-test": ["text", "image"],
        "kimi-test": ["text", "image"],
      },
    );
    assert.equal(catalogs.agentRoles.length, catalog.models.length);
    assert.equal(
      new Set(catalogs.agentRoles.map((role) => role.name)).size,
      catalogs.agentRoles.length,
    );
    for (const [provider, model] of [
      ["openai", "gpt-5.6-sol"],
      ["deepseek", "deepseek-test"],
      ["deepseek", "deepseek-v4-flash-vision-exp"],
      ["grok", "grok-test"],
      ["kimi", "kimi-test"],
    ]) {
      const role = catalogs.agentRoles.find(
        (value) => value.provider === provider && value.model === model,
      );
      assert(role, `missing generated ${provider}/${model} agent role`);
      const roleFile = path.join(
        stateDir,
        "home",
        "agents",
        "alta-generated",
        `${role.name}.toml`,
      );
      const roleConfig = fs.readFileSync(roleFile, "utf8");
      assert.match(
        roleConfig,
        new RegExp(`name = ${JSON.stringify(role.name)}`),
      );
      assert.match(
        roleConfig,
        new RegExp(`model_provider = ${JSON.stringify(provider)}`),
      );
      assert.match(roleConfig, new RegExp(`model = ${JSON.stringify(model)}`));
      assert.match(roleConfig, /developer_instructions = /);
      assert.match(roleConfig, /alta_web_research/);
      assert.match(roleConfig, /alta_web_archive/);
      assert.match(roleConfig, /alta_social_read/);
      assert.match(roleConfig, /alta_tradingview_navigate/);
      assert.match(roleConfig, /TradingView is display-only/);
      assert.match(
        roleConfig,
        /never pass its URLs to fetch, batch-fetch, crawl, research, sitemap, feed, social-read, or archive/,
      );
      assert.match(roleConfig, /alta_file_read/);
      assert.match(roleConfig, /objective, required deliverable, constraints/);
      assert.match(roleConfig, /Avoid duplicate work and status chatter/);
      assert.match(roleConfig, /never copy base64 into agent messages/);
      assert.match(roleConfig, /Text-only agents must delegate media/);
      assert.ok(Buffer.byteLength(roleConfig) < 2_500);
      assert.equal(fs.statSync(roleFile).mode & 0o777, 0o600);
    }

    const agentsDir = path.join(stateDir, "home", "agents");
    const customRole = path.join(agentsDir, "custom.toml");
    const staleGeneratedRole = path.join(
      agentsDir,
      "alta-generated",
      "stale.toml",
    );
    fs.writeFileSync(customRole, 'name = "custom"\n');
    fs.writeFileSync(staleGeneratedRole, 'name = "stale"\n');
    writeCatalogs(rootDir, stateDir, [
      {
        id: "deepseek-test",
        provider: "deepseek",
        context_window: 128_000,
        reasoning: true,
        image: false,
      },
    ]);
    assert(fs.existsSync(customRole));
    assert(!fs.existsSync(staleGeneratedRole));

    const configFile = writeConfig(stateDir, {
      agentThreads: 6,
    });
    const config = fs.readFileSync(configFile, "utf8");
    assert.match(config, /max_concurrent_threads_per_session = 6/);
    assert.match(config, /multi_agent_v2 = true/);
    assert.match(config, /web_search = "disabled"/);
    assert.match(config, /apps = false/);
    assert.match(config, /remote_plugin = false/);
    assert.match(config, /\[mcp_servers\.alta_internet\]/);
    assert.match(config, /bearer_token_env_var = "ALTA_GATEWAY_TOKEN"/);
    assert.match(config, /default_tools_approval_mode = "approve"/);
    assert.match(config, /alta_web_sitemap/);
    assert.match(config, /alta_social_read/);
    assert.match(config, /alta_tradingview_navigate/);
    assert.match(config, /TradingView is display-only/);
    assert.match(
      config,
      /never pass its URLs to fetch, batch-fetch, crawl, research, sitemap, feed, social-read, or archive/,
    );
    assert.match(config, /alta_file_read/);
    assert.match(config, /compact task packets/);
    assert.match(config, /shared workspace/);
    assert.match(config, /create a bounded transcript/);
    for (const provider of ["deepseek", "grok", "kimi"])
      assert.match(config, new RegExp(`\\[model_providers\\.${provider}\\]`));
    assert.doesNotMatch(config, /\[model_providers\.alta\]/);
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("catalog rejects model IDs that cannot be routed unambiguously", () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "alta-catalog-"));
  try {
    assert.throws(
      () =>
        writeCatalogs(rootDir, stateDir, [
          {
            id: "shared-model",
            provider: "deepseek",
            context_window: 128_000,
            reasoning: true,
            image: false,
          },
          {
            id: "shared-model",
            provider: "xai",
            context_window: 128_000,
            reasoning: true,
            image: false,
          },
        ]),
      /ambiguous between deepseek and xai/,
    );
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("legacy provider caches refresh once for newly supported models", async () => {
  const stateDir = fs.mkdtempSync(
    path.join(os.tmpdir(), "alta-catalog-cache-"),
  );
  const cacheDir = path.join(stateDir, "cache");
  const cacheFile = path.join(cacheDir, "provider-models.json");
  fs.mkdirSync(cacheDir);
  fs.writeFileSync(
    cacheFile,
    JSON.stringify({
      models: [
        {
          id: "kimi-k3",
          provider: "kimi",
          context_window: 262_144,
          reasoning: true,
        },
      ],
    }),
  );
  try {
    const refreshed = await resolveProviderModels(rootDir, stateDir, {});
    assert.equal(refreshed.fromCache, false);
    const vision = refreshed.models.find(
      (model) => model.id === "deepseek-v4-flash-vision-exp",
    );
    assert.deepEqual(vision.input_modalities, ["text", "image"]);
    const kimi = refreshed.models.find((model) => model.id === "kimi-k3");
    assert.deepEqual(kimi.input_modalities, ["text", "image"]);
    assert.equal(kimi.video, true);

    const cached = await resolveProviderModels(rootDir, stateDir, {});
    assert.equal(cached.fromCache, true);
    assert.deepEqual(
      cached.models.find((model) => model.id === "deepseek-v4-flash-vision-exp")
        .input_modalities,
      ["text", "image"],
    );
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});
