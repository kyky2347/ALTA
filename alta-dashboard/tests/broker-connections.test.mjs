import assert from "node:assert/strict";
import test from "node:test";
import {
  validBrokerCatalog,
  validBrokerVerification,
  brokerCredentialFields,
  brokerFieldKind,
  brokerConnectionError,
} from "../src/lib/broker-connections.ts";

test("broker inputs distinguish gateways, key material and secrets", () => {
  assert.equal(brokerFieldKind("private_key"), "key");
  assert.equal(brokerFieldKind("port"), "number");
  assert.equal(brokerFieldKind("client_id"), "number");
  assert.equal(brokerFieldKind("security_firm"), "firm");
  assert.equal(brokerFieldKind("access_token"), "secret");
  assert.equal(
    brokerConnectionError("account_environment_mismatch"),
    "brokerFieldsInvalid",
  );
  assert.equal(
    brokerConnectionError("broker_connection_timed_out"),
    "brokerConnectionTimeout",
  );
  assert.equal(
    brokerConnectionError("secret-reply"),
    "brokerConnectionUnavailable",
  );
});

const rows = () =>
  ["tiger", "alpaca", "ibkr", "futu", "longport", "schwab"].map((provider) => ({
    provider,
    name: provider,
    docs: "https://docs.alpaca.markets/us/docs/getting-started-with-trading-api",
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
    rows().map((r) => ({ ...r, docs: "javascript:alert(1)" })),
    rows().map((r) => ({ ...r, environment: "LIVE" })),
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
