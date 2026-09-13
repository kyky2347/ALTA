import assert from "node:assert/strict";
import test from "node:test";
import {
  EXECUTION_PROVIDERS,
  validBrokerRoute,
  executionFailure,
} from "../src/lib/broker-execution.ts";

test("execution destination is explicit, exact and never inferred from a missing response", () => {
  const shadow = {
    provider: null,
    environment: null,
    binding: null,
    profile_revision: null,
    revision: "a".repeat(64),
  };
  assert.equal(validBrokerRoute(shadow), true);
  for (const provider of EXECUTION_PROVIDERS) {
    const route = {
      ...shadow,
      provider,
      environment: "LIVE",
      binding: "b".repeat(64),
      profile_revision: "c".repeat(64),
    };
    assert.equal(validBrokerRoute(route), true);
    for (const field of [
      "binding",
      "revision",
      "profile_revision",
      "environment",
    ])
      assert.equal(validBrokerRoute({ ...route, [field]: null }), false);
  }
  for (const route of [
    null,
    {},
    { ...shadow, provider: "unknown" },
    { ...shadow, environment: "LIVE" },
  ])
    assert.equal(validBrokerRoute(route), false);
});

test("broker failures remain actionable without returning arbitrary provider error text", () => {
  assert.equal(
    executionFailure("execution_broker_not_selected"),
    "brokerRouteConflict",
  );
  assert.equal(
    executionFailure("execution_runtime_must_be_stopped"),
    "executionStopFirst",
  );
  assert.equal(
    executionFailure("broker_identity_unverified"),
    "brokerAuthorizationEvidenceMissing",
  );
  assert.equal(
    executionFailure("sensitive provider response"),
    "brokerActionUnconfirmed",
  );
});
