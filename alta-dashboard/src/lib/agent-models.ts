export const MODEL_ROLES = [
  "scout",
  "thesis",
  "disconfirming",
  "moderator",
  "expression",
  "audit",
  "position",
] as const;
export type ModelRole = (typeof MODEL_ROLES)[number];
export type ModelRoute = { provider: string; model: string };
export type AgentModels = {
  roles: Record<ModelRole, ModelRoute>;
  scouts: Record<string, ModelRoute>;
};
export type AgentModelState = {
  revision: string;
  settings: AgentModels;
  scoutIds: string[];
  providers: string[];
};

// Validate the transport shape before rendering. Semantic route errors remain
// editable through modelProblem; a malformed response must never unlock Save.
export function validAgentModelState(value: unknown): value is AgentModelState {
  const record = (item: unknown): item is Record<string, unknown> =>
    typeof item === "object" && item !== null && !Array.isArray(item);
  const route = (item: unknown) =>
    record(item) &&
    typeof item.provider === "string" &&
    typeof item.model === "string";
  if (!record(value) || !record(value.settings)) return false;
  const { roles, scouts } = value.settings;
  return (
    typeof value.revision === "string" &&
    value.revision.length > 0 &&
    Array.isArray(value.providers) &&
    value.providers.length > 0 &&
    value.providers.every((provider) => typeof provider === "string") &&
    Array.isArray(value.scoutIds) &&
    value.scoutIds.every((id) => typeof id === "string") &&
    record(roles) &&
    MODEL_ROLES.every((id) => route(roles[id])) &&
    Object.values(roles).every(route) &&
    record(scouts) &&
    Object.values(scouts).every(route)
  );
}
export function validModelRoute(route: ModelRoute): boolean {
  const prefixes: Record<string, string> = {
    openai: "gpt-",
    deepseek: "deepseek-",
    grok: "grok-",
    kimi: "kimi-",
  };
  return (
    Object.hasOwn(prefixes, route.provider) &&
    /^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$/.test(route.model) &&
    route.model.toLowerCase().startsWith(prefixes[route.provider])
  );
}
export function modelProblem(settings: AgentModels): string | null {
  for (const route of [
    ...Object.values(settings.roles),
    ...Object.values(settings.scouts),
  ]) {
    if (!validModelRoute(route)) return "model_route_invalid";
  }
  const same = (a: ModelRole, b: ModelRole) =>
    settings.roles[a].provider === settings.roles[b].provider &&
    settings.roles[a].model.toLowerCase() ===
      settings.roles[b].model.toLowerCase();
  if (same("thesis", "disconfirming")) return "debate_models_must_differ";
  if (same("expression", "audit")) return "audit_model_must_differ";
  return null;
}
