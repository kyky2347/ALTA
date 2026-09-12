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
