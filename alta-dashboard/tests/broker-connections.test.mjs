import assert from "node:assert/strict";
import test from "node:test";
import {
  validBrokerCatalog,
  validBrokerVerification,
  brokerCredentialFields,
  brokerFieldKind,
  brokerConnectionError,
  validBrokerAccountState,
  BROKER_CHECKS,
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
      equity: "1000.00",
      cash: "500.00",
      buying_power: "500.00",
      positions: [],
      orders: [],
    },
  };
  assert.equal(validBrokerVerification(response), true);
  assert.equal(
    validBrokerVerification({
      ...response,
      snapshot: { ...response.snapshot, cash: "0E-8" },
    }),
    true,
  );
  assert.equal(
    validBrokerVerification({
      ...response,
      snapshot: { ...response.snapshot, cash: "NaN" },
    }),
    false,
  );
  assert.equal(
    validBrokerVerification({
      ...response,
      snapshot: { ...response.snapshot, orders: [null] },
    }),
    false,
  );
  assert.equal(
    validBrokerVerification({
      ...response,
      snapshot: { ...response.snapshot, positions: null },
    }),
    false,
  );
});

test("authorization review is account-bound and cannot claim unreleased execution", () => {
  const binding = "a".repeat(64);
  const revision = "b".repeat(64);
  const review = {
    eligible: false,
    provider: "alpaca",
    environment: "PAPER",
    binding,
    revision,
    checks: Object.fromEntries(BROKER_CHECKS.map((k) => [k, false])),
    limits: {
      max_order_notional: "10000",
      max_gross_notional: "25000",
      max_quote_age_seconds: 10,
    },
  };
  const value = {
    provider: "alpaca",
    environment: "PAPER",
    binding,
    revision,
    authority: "off",
    verification: { status: "not_checked", fresh: false, snapshot: null },
    authorization_review: review,
  };
  assert.equal(validBrokerAccountState(value), true);
  for (const change of [
    { eligible: true },
    { binding: "c".repeat(64) },
    { revision: "c".repeat(64) },
    { environment: "LIVE" },
    { checks: { ...review.checks, account_acceptance: true } },
    { limits: { ...review.limits, max_order_notional: "Infinity" } },
  ])
    assert.equal(
      validBrokerAccountState({
        ...value,
        authorization_review: { ...review, ...change },
      }),
      false,
    );
  assert.equal(
    validBrokerAccountState({
      ...value,
      verification: { ...value.verification, fresh: true },
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
