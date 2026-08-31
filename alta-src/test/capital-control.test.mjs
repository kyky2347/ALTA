import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { PaperCapitalControl } from "../capital-control.mjs";

const PAPER_ACCOUNT = "00000000000000000";

function fixture(context) {
  const rootDir = fs.mkdtempSync(
    path.join(os.tmpdir(), "alta-capital-control-"),
  );
  context.after(() => fs.rmSync(rootDir, { recursive: true, force: true }));
  const stateDir = path.join(rootDir, ".alta");
  const credentialsDir = path.join(rootDir, "credentials");
  const brokerDir = path.join(credentialsDir, "broker");
  fs.mkdirSync(brokerDir, { recursive: true, mode: 0o700 });
  const configuration = path.join(brokerDir, "tiger-paper.properties");
  fs.writeFileSync(
    configuration,
    [
      `account=${PAPER_ACCOUNT}`,
      "tiger_id=synthetic-id",
      "private_key_pk8=synthetic-private-key",
      "",
    ].join("\n"),
    { mode: 0o600 },
  );
  const controller = new PaperCapitalControl({
    rootDir,
    stateDir,
    environment: () => ({ ALTA_CREDENTIALS_DIR: credentialsDir }),
  });
  return { controller, configuration, rootDir, stateDir };
}

function snapshot(accountFingerprint, update = {}) {
  return {
    paper: true,
    accountBinding: true,
    accountFingerprint,
    observedAt: "2026-08-30T10:00:00+00:00",
    brokerUpdatedAt: "2026-08-30T10:00:00+00:00",
    positionCount: 0,
    openOrderCount: 0,
    recentOrderCount: 0,
    mutationPolicy: "one_share_limit_day",
    assets: {
      currency: "USD",
      cashBalance: null,
      cashAvailableForTrade: null,
      netLiquidation: null,
      grossPositionValue: null,
      buyingPower: null,
      unrealizedPnl: null,
      realizedPnl: null,
      maintenanceMargin: null,
    },
    positions: [],
    orders: [],
    ...update,
  };
}

test("Paper capital authorization is durable, account-bound, and fail-closed", async (context) => {
  const { controller, configuration } = fixture(context);
  const accountFingerprint = controller.configuration().accountFingerprint;
  controller.invoke = async () => snapshot(accountFingerprint);

  assert.equal(controller.status().enabled, false);
  const enabled = await controller.setEnabled(true);
  assert.equal(enabled.enabled, true);
  assert.equal(enabled.posture, "paper_enabled");
  assert.equal(enabled.audit[0].action, "authorization_enabled");
  const environment = controller.runtimeEnvironment();
  assert.equal(environment.ALTA_TIGER_PAPER_ENABLED, "1");
  assert.equal(environment.ALTA_TIGER_CONFIG_PATH, configuration);
  assert.match(environment.ALTA_TIGER_PAPER_ACCOUNT_SHA256, /^[a-f0-9]{64}$/);
  assert.equal(JSON.stringify(enabled).includes(PAPER_ACCOUNT), false);

  fs.appendFileSync(configuration, "language=en_US\n");
  const changed = controller.status();
  assert.equal(changed.requestedEnabled, true);
  assert.equal(changed.enabled, false);
  assert.equal(changed.posture, "configuration_changed");
  assert.deepEqual(controller.runtimeEnvironment(), {
    ALTA_TIGER_PAPER_ENABLED: "0",
  });

  const disabled = await controller.setEnabled(false);
  assert.equal(disabled.enabled, false);
  assert.equal(disabled.requestedEnabled, false);
  assert.equal(disabled.audit[0].action, "authorization_disabled");
});

test("Paper capital authorization refuses existing positions or orders", async (context) => {
  const { controller } = fixture(context);
  const accountFingerprint = controller.configuration().accountFingerprint;
  controller.invoke = async () =>
    snapshot(accountFingerprint, { positionCount: 1 });

  await assert.rejects(
    () => controller.setEnabled(true),
    /empty account and no open orders/,
  );
  assert.equal(controller.status().enabled, false);
  assert.equal(controller.status().audit[0].result, "failed");
});

test("Paper capital refresh stores only sanitized broker state", async (context) => {
  const { controller } = fixture(context);
  const accountFingerprint = controller.configuration().accountFingerprint;
  controller.invoke = async () =>
    snapshot(accountFingerprint, {
      positionCount: 1,
      recentOrderCount: 1,
      rawAccount: PAPER_ACCOUNT,
      positions: [
        {
          account: PAPER_ACCOUNT,
          symbol: "SPY",
          securityType: "STK",
          currency: "USD",
          quantity: "1",
          averageCost: "100",
          marketPrice: "101",
          marketValue: "101",
          unrealizedPnl: "1",
          unrealizedPnlPercent: "0.01",
          realizedPnl: "0",
          todayPnl: "1",
          salableQuantity: "1",
        },
      ],
      orders: [
        {
          id: PAPER_ACCOUNT,
          reference: "0123456789abcdef",
          symbol: "SPY",
          securityType: "STK",
          side: "BUY",
          orderType: "LMT",
          status: "FILLED",
          quantity: "1",
          filled: "1",
          remaining: "0",
          limitPrice: "100",
          averageFillPrice: "100",
          commission: "0.01",
          realizedPnl: "0",
          timeInForce: "DAY",
          outsideRegularHours: false,
          createdAt: "2026-08-30T10:00:00+00:00",
          updatedAt: "2026-08-30T10:00:01+00:00",
          filledAt: "2026-08-30T10:00:01+00:00",
        },
      ],
    });

  const refreshed = await controller.refresh();
  assert.equal(refreshed.snapshot.positions[0].symbol, "SPY");
  assert.equal(JSON.stringify(refreshed).includes(PAPER_ACCOUNT), false);
  assert.equal(refreshed.audit[0].action, "preflight_refreshed");

  const stored = JSON.parse(fs.readFileSync(controller.snapshotFile, "utf8"));
  stored.rawAccount = PAPER_ACCOUNT;
  stored.assets.rawBrokerPayload = { credential: "must-not-cross-boundary" };
  fs.writeFileSync(controller.snapshotFile, JSON.stringify(stored));
  const projected = controller.status();
  assert.equal(JSON.stringify(projected).includes(PAPER_ACCOUNT), false);
  assert.equal(
    JSON.stringify(projected).includes("must-not-cross-boundary"),
    false,
  );
});

test("Paper capital state corruption fails closed and disabled recovery is durable", async (context) => {
  const { controller, stateDir } = fixture(context);
  const accountFingerprint = controller.configuration().accountFingerprint;
  controller.invoke = async () => snapshot(accountFingerprint);

  await controller.setEnabled(true);
  fs.unlinkSync(controller.snapshotFile);
  const missingSnapshot = controller.status();
  assert.equal(missingSnapshot.requestedEnabled, true);
  assert.equal(missingSnapshot.enabled, false);
  assert.equal(missingSnapshot.posture, "snapshot_invalid");
  assert.match(missingSnapshot.snapshotError, /missing/);
  assert.deepEqual(controller.runtimeEnvironment(), {
    ALTA_TIGER_PAPER_ENABLED: "0",
  });

  await controller.setEnabled(true);
  fs.writeFileSync(controller.authorizationFile, "{\n");
  const invalidAuthorization = controller.status();
  assert.equal(invalidAuthorization.enabled, false);
  assert.equal(invalidAuthorization.posture, "authorization_invalid");
  assert.match(invalidAuthorization.authorizationError, /JSON/);

  const recovered = await controller.setEnabled(false);
  assert.equal(recovered.enabled, false);
  assert.equal(recovered.requestedEnabled, false);
  assert.equal(recovered.authorizationError, null);

  fs.writeFileSync(controller.snapshotFile, "{\n");
  const invalidSnapshot = controller.status();
  assert.equal(invalidSnapshot.enabled, false);
  assert.equal(invalidSnapshot.posture, "snapshot_invalid");
  assert.equal(invalidSnapshot.snapshot, null);
  assert.match(invalidSnapshot.snapshotError, /JSON/);
  assert.equal(fs.statSync(path.join(stateDir, "runtime")).isDirectory(), true);
});
