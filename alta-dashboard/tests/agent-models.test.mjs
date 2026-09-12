import assert from "node:assert/strict";
import test from "node:test";
import {
  MODEL_ROLES,
  modelProblem,
  validAgentModelState,
} from "../src/lib/agent-models.ts";

function state() {
  return {
    revision: "test-revision",
    providers: ["openai", "deepseek"],
    scoutIds: ["change-event"],
    settings: {
      roles: Object.fromEntries(
        MODEL_ROLES.map((id) => [
          id,
          { provider: "openai", model: `gpt-${id}` },
        ]),
      ),
      scouts: {},
    },
  };
}

test("model settings validate a complete response before enabling the editor", () => {
  assert.equal(validAgentModelState(state()), true);
  for (const invalid of [
    null,
    [],
    {},
    { ...state(), revision: "" },
    { ...state(), providers: null },
    { ...state(), scoutIds: [null] },
  ]) {
    assert.equal(validAgentModelState(invalid), false);
  }
});

test("missing roles and malformed scout overrides fail closed", () => {
  const missing = state();
  delete missing.settings.roles.audit;
  assert.equal(validAgentModelState(missing), false);
  const broken = state();
  broken.settings.scouts["change-event"] = { provider: "openai", model: null };
  assert.equal(validAgentModelState(broken), false);
  const extra = state();
  extra.settings.roles.unexpected = null;
  assert.equal(validAgentModelState(extra), false);
});

test("validly shaped but invalid routes can be displayed for correction, never saved", () => {
  const value = state();
  value.settings.roles.scout.model = "";
  assert.equal(validAgentModelState(value), true);
  assert.equal(modelProblem(value.settings), "model_route_invalid");
});

test("independent reviewers cannot silently share a model", () => {
  const value = state();
  assert.equal(modelProblem(value.settings), null);
  value.settings.roles.disconfirming = { ...value.settings.roles.thesis };
  assert.equal(modelProblem(value.settings), "debate_models_must_differ");
  const audit = state();
  audit.settings.roles.audit = { ...audit.settings.roles.expression };
  assert.equal(modelProblem(audit.settings), "audit_model_must_differ");
});
