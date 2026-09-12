import assert from "node:assert/strict";
import test from "node:test";
import {
  validBrokerCatalog,
  validBrokerVerification,
  brokerCredentialFields,
} from "../src/lib/broker-connections.ts";

const rows = () =>
  ["tiger", "alpaca", "ibkr", "futu", "longport", "schwab"].map((provider) => ({
    provider,
    name: provider,
    configured: false,
    revision: "new",
    fields: ["api_key"],
    authentication: "key_pair",
    environments: ["PAPER"],
    autonomous_execution: false,
    acceptance: "not_verified",
  }));
test("broker catalog rejects missing, duplicate, unknown, and falsely activated providers", () => {
  assert.equal(validBrokerCatalog({ brokers: rows() }), true);
  for (const brokers of [
    rows().slice(1),
    [...rows().slice(1), rows()[1]],
    rows().map((r) => ({ ...r, fields: ["unknown_secret"] })),
    rows().map((r) => ({ ...r, autonomous_execution: true })),
  ])
    assert.equal(validBrokerCatalog({ brokers }), false);
});

test("broker verification requires typed account proof and complete collection shapes", () => {
  assert.equal(validBrokerVerification({ provider: "alpaca" }), false);
  assert.equal(
    validBrokerVerification({
      provider: "alpaca",
      snapshot: { verified_at: "invalid" },
    }),
    false,
  );
  const response = {
    provider: "alpaca",
    snapshot: {
      verified_at: new Date().toISOString(),
      account_verified: true,
      environment_verified: true,
      trading_permitted: false,
      currency: "USD",
      positions: [],
      orders: [],
    },
  };
  assert.equal(validBrokerVerification(response), true);
  assert.equal(
    validBrokerVerification({
      ...response,
      snapshot: { ...response.snapshot, positions: null },
    }),
    false,
  );
});

test("Futu Paper never asks for a live trading password", () => {
  const broker = {
    ...rows()[3],
    fields: ["port", "security_firm", "trade_password"],
  };
  assert.deepEqual(brokerCredentialFields(broker, "PAPER"), [
    "port",
    "security_firm",
  ]);
  assert.deepEqual(brokerCredentialFields(broker, "LIVE"), broker.fields);
});
