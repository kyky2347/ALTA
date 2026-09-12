import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { acquireLease } from "./storage.mjs";
import { atomicWriteJson } from "./durable-file.mjs";

export const MODEL_ROLES = Object.freeze({
  scout: ["AGENT", "deepseek", "deepseek-v4-flash"],
  thesis: ["THESIS", "deepseek", "deepseek-v4-pro"],
  disconfirming: ["DISCONFIRMING", "grok", "grok-4.6"],
  moderator: ["MODERATOR", "kimi", "kimi-k3"],
  expression: ["EXPRESSION", "deepseek", "deepseek-v4-pro"],
  audit: ["AUDIT", "grok", "grok-4.6"],
  position: ["POSITION", "deepseek", "deepseek-v4-flash"],
});
export const SCOUT_IDS = Object.freeze([
  "change_event_scout",
  "market_dislocation_scout",
  "causal_policy_scout",
  "expectation_gap_scout",
]);
const PREFIXES = {
  openai: "gpt-",
  deepseek: "deepseek-",
  grok: "grok-",
  kimi: "kimi-",
};
const object = (value) =>
  value && typeof value === "object" && !Array.isArray(value);
function reject(code, statusCode = 400) {
  throw Object.assign(new Error(code), { code, statusCode });
}
function route(value) {
  if (
    !object(value) ||
    Object.keys(value).sort().join() !== "model,provider" ||
    !Object.hasOwn(PREFIXES, value.provider) ||
    typeof value.model !== "string" ||
    !/^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$/.test(value.model) ||
    !value.model.toLowerCase().startsWith(PREFIXES[value.provider])
  )
    reject("model_route_invalid");
  return { provider: value.provider, model: value.model };
}
export function validateModelSettings(value) {
  if (
    !object(value) ||
    Object.keys(value).sort().join() !== "roles,scouts" ||
    !object(value.roles) ||
    !object(value.scouts) ||
    Object.keys(value.roles).sort().join() !==
      Object.keys(MODEL_ROLES).sort().join() ||
    Object.keys(value.scouts).some((id) => !SCOUT_IDS.includes(id))
  )
    reject("model_settings_invalid");
  const roles = Object.fromEntries(
    Object.keys(MODEL_ROLES).map((id) => [id, route(value.roles[id])]),
  );
  const scouts = Object.fromEntries(
    SCOUT_IDS.filter((id) => Object.hasOwn(value.scouts, id)).map((id) => [
      id,
      route(value.scouts[id]),
    ]),
  );
  const same = (a, b) =>
    roles[a].provider === roles[b].provider &&
    roles[a].model.toLowerCase() === roles[b].model.toLowerCase();
  if (same("thesis", "disconfirming")) reject("debate_models_must_differ");
  if (same("expression", "audit")) reject("audit_model_must_differ");
  return { roles, scouts };
}
function defaults(environment) {
  return validateModelSettings({
    roles: Object.fromEntries(
      Object.entries(MODEL_ROLES).map(([id, [key, provider, model]]) => [
        id,
        {
          provider:
            environment[`ALTA_${key}_PROVIDER`] ??
            (id === "position" ? environment.ALTA_AGENT_PROVIDER : undefined) ??
            provider,
          model:
            environment[`ALTA_${key}_MODEL`] ??
            (id === "position" ? environment.ALTA_AGENT_MODEL : undefined) ??
            model,
        },
      ]),
    ),
    scouts: JSON.parse(environment.ALTA_SCOUT_MODEL_OVERRIDES ?? "{}"),
  });
}

/** Operator-owned, atomic configuration. Never exposed to research tools. */
export class AgentModelSettings {
  constructor(stateDir, environment) {
    this.file = path.join(stateDir, "config", "agent-models.json");
    this.environment = environment;
  }
  read() {
    let settings;
    try {
      const stat = fs.lstatSync(this.file);
      if (
        !stat.isFile() ||
        stat.isSymbolicLink() ||
        stat.size > 16384 ||
        (process.platform !== "win32" &&
          (stat.mode & 0o077 || stat.uid !== process.getuid()))
      )
        reject("model_settings_file_unsafe", 503);
      const saved = JSON.parse(fs.readFileSync(this.file, "utf8"));
      if (saved.version !== 1) reject("model_settings_invalid", 503);
      settings = validateModelSettings(saved.settings);
    } catch (error) {
      if (error.code !== "ENOENT") reject("model_settings_unreadable", 503);
      settings = defaults(this.environment());
    }
    return {
      revision: createHash("sha256")
        .update(JSON.stringify(settings))
        .digest("hex"),
      settings,
      scoutIds: SCOUT_IDS,
      providers: Object.keys(PREFIXES),
    };
  }
  save(request) {
    if (
      !object(request) ||
      Object.keys(request).sort().join() !== "revision,settings" ||
      !/^[a-f0-9]{64}$/.test(request.revision ?? "")
    )
      reject("model_settings_invalid");
    const settings = validateModelSettings(request.settings);
    const lease = acquireLease(`${this.file}.lock`);
    try {
      if (this.read().revision !== request.revision)
        reject("model_settings_conflict", 409);
      atomicWriteJson(this.file, { version: 1, settings });
      return this.read();
    } finally {
      lease.release();
    }
  }
  runtimeEnvironment() {
    const { settings } = this.read();
    return {
      ...Object.fromEntries(
        Object.entries(MODEL_ROLES).flatMap(([id, [key]]) => [
          [`ALTA_${key}_PROVIDER`, settings.roles[id].provider],
          [`ALTA_${key}_MODEL`, settings.roles[id].model],
        ]),
      ),
      ALTA_SCOUT_MODEL_OVERRIDES: JSON.stringify(settings.scouts),
    };
  }
}
