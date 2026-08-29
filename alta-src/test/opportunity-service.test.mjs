import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import net from "node:net";
import { OpportunityService } from "../opportunity-service.mjs";

function fixture(t, sourceEnv = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "alta-service-"));
  const state = path.join(root, ".alta");
  const credentialRoot = path.join(root, "external-credentials");
  const resources = path.join(credentialRoot, "resources");
  fs.mkdirSync(resources, { recursive: true, mode: 0o700 });
  fs.writeFileSync(
    path.join(resources, "Massive.rtf"),
    "service_fixture_123456789012345678901234",
    { mode: 0o600 },
  );
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const platform = {
    platform: "darwin",
    home: root,
    definitionPath: () => path.join(root, "service.plist"),
    install: () => path.join(root, "service.plist"),
    status: () => ({ code: 1, stdout: "", stderr: "" }),
  };
  return {
    root,
    state,
    service: new OpportunityService({
      rootDir: root,
      stateDir: state,
      cliFile: path.join(root, "alta-src", "cli.mjs"),
      sourceEnv: {
        PATH: "/usr/bin",
        ALTA_CREDENTIALS_DIR: credentialRoot,
        ...sourceEnv,
      },
      platform,
      environmentFactory: () => null,
    }),
  };
}

test("managed configuration is autonomous, owner-only, and secret-free", (t) => {
  const { service } = fixture(t, {
    MASSIVE_API_KEY: "must_not_be_persisted_12345678901234567890",
    ALTA_TIGER_PAPER_ENABLED: "1",
    ALTA_TIGER_CONFIG_PATH: "/fixture/paper.properties",
    ALTA_TIGER_PAPER_ACCOUNT_SHA256: "fixture-account-hash",
    TIGER_PRIVATE_KEY: "fixture-private-key",
    ALTA_SHADOW_REFERENCE_NAV: "2000000",
    ALTA_SHADOW_TRADE_LOSS_BUDGET_BPS: "20",
    ALTA_SHADOW_MAX_POSITION_NAV_BPS: "75",
    ALTA_SHADOW_MAX_GROSS_NAV_BPS: "600",
    ALTA_SHADOW_EQUITY_STRESS_FLOOR_BPS: "3000",
    ALTA_SHADOW_MAX_EXIT_DAYS: "3",
    ALTA_SHADOW_ADV_PARTICIPATION_BPS: "250",
    ALTA_SHADOW_MIN_NET_ALPHA_BPS: "80",
  });

  const { environment, credentialSources } = service.runtimeEnvironment();
  const persisted = fs.readFileSync(service.configFile, "utf8");
  const definition = service.definition();

  assert.equal(environment.ALTA_ENVIRONMENT, "shadow");
  assert.equal(environment.ALTA_AUTONOMOUS_ENABLED, "1");
  assert.equal(environment.ALTA_TIGER_PAPER_ENABLED, "0");
  assert.equal(environment.ALTA_TIGER_CONFIG_PATH, undefined);
  assert.equal(environment.ALTA_TIGER_PAPER_ACCOUNT_SHA256, undefined);
  assert.equal(environment.TIGER_PRIVATE_KEY, undefined);
  assert.equal(environment.ALTA_MASSIVE_ENABLED, "1");
  assert.equal(environment.ALTA_SHADOW_REFERENCE_NAV, "2000000");
  assert.equal(environment.ALTA_SHADOW_TRADE_LOSS_BUDGET_BPS, "20");
  assert.equal(environment.ALTA_SHADOW_MAX_POSITION_NAV_BPS, "75");
  assert.equal(environment.ALTA_SHADOW_MAX_GROSS_NAV_BPS, "600");
  assert.equal(environment.ALTA_SHADOW_EQUITY_STRESS_FLOOR_BPS, "3000");
  assert.equal(environment.ALTA_SHADOW_MAX_EXIT_DAYS, "3");
  assert.equal(environment.ALTA_SHADOW_ADV_PARTICIPATION_BPS, "250");
  assert.equal(environment.ALTA_SHADOW_MIN_NET_ALPHA_BPS, "80");
  assert.match(environment.ALTA_CREDENTIAL_REVISION, /^[a-f0-9]{16}$/);
  assert.equal(environment.ALTA_CREDENTIAL_SLOTS, "massive");
  assert.equal(persisted.includes(environment.MASSIVE_API_KEY), false);
  assert.equal(persisted.includes(environment.ALTA_API_TOKEN), false);
  assert.equal(persisted.includes("paper.properties"), false);
  assert.equal(persisted.includes("fixture-account-hash"), false);
  assert.equal(definition.includes(environment.MASSIVE_API_KEY), false);
  assert.equal(definition.includes(environment.ALTA_API_TOKEN), false);
  assert.equal(fs.statSync(service.configFile).mode & 0o777, 0o600);
  assert.equal(fs.statSync(service.tokenFile).mode & 0o777, 0o600);
  assert.match(credentialSources.MASSIVE_API_KEY, /environment/);
});

test("foreground service bootstraps dependencies, migrates, and supervises", async (t) => {
  const calls = [];
  const { service } = fixture(t);
  service.environmentFactory = (environment) => ({
    up: async () => calls.push("up"),
    python: async (args, options) => {
      calls.push({ command: args.join(" "), timeoutMs: options.timeoutMs });
      assert.equal(environment.ALTA_AUTONOMOUS_ENABLED, "1");
      return 0;
    },
  });

  const code = await service.run();
  const state = JSON.parse(fs.readFileSync(service.stateFile, "utf8"));

  assert.equal(code, 0);
  assert.deepEqual(calls, [
    "up",
    {
      command: "-m alta_asterism migrate upgrade",
      timeoutMs: 300_000,
    },
    {
      command: `-m alta_asterism supervisor --host 127.0.0.1 --port 8876 --state-file ${service.supervisorStateFile}`,
      timeoutMs: undefined,
    },
  ]);
  assert.equal(state.state, "exited");
  assert.equal(state.exitCode, 0);
  assert.equal(fs.existsSync(service.lockFile), false);
});

test("service status detects a credential revision that needs reload", async (t) => {
  const { service } = fixture(t);
  service.ensureConfiguration();
  service.writeState("running", {
    credentialRevision: "0000000000000000",
    credentialSlots: [],
  });

  const status = await service.status();

  assert.equal(status.credentials.valid, true);
  assert.match(status.credentials.currentRevision, /^[a-f0-9]{16}$/);
  assert.equal(status.credentials.loadedRevision, "0000000000000000");
  assert.equal(status.credentials.reloadRequired, true);
  assert.deepEqual(status.credentials.configuredSlots, ["massive"]);
});

test("installation rejects an occupied endpoint before starting dependencies", async (t) => {
  const listener = net.createServer();
  await new Promise((resolve) => listener.listen(0, "127.0.0.1", resolve));
  t.after(() => listener.close());
  const address = listener.address();
  const { service } = fixture(t, { ALTA_SERVICE_PORT: String(address.port) });

  await assert.rejects(
    service.assertEndpointAvailable(),
    /endpoint .* is already in use/,
  );
});
