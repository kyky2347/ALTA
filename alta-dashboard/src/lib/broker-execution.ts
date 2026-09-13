export const EXECUTION_PROVIDERS = [
  "tiger",
  "alpaca",
  "ibkr",
  "futu",
  "longport",
  "schwab",
] as const;
export type BrokerProvider = (typeof EXECUTION_PROVIDERS)[number];
export type BrokerRoute = {
  provider: BrokerProvider | null;
  binding: string | null;
  profile_revision: string | null;
  environment: "PAPER" | "LIVE" | null;
  revision: string;
};
export type BrokerExecutionRequest =
  | {
      action: "select";
      provider: string | null;
      revision: string;
      profile_revision: string | null;
    }
  | { action: "verify"; provider: string }
  | {
      action: "authorize";
      provider: string;
      revision: string;
      confirmation: string;
    }
  | { action: "revoke" | "reconcile"; provider: string; revision: string };

export function validBrokerRoute(value: unknown): value is BrokerRoute {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  const hash = (s: unknown) =>
    typeof s === "string" && /^[a-f0-9]{64}$/.test(s);
  return (
    hash(v.revision) &&
    (v.provider === null
      ? v.binding === null &&
        v.profile_revision === null &&
        v.environment === null
      : EXECUTION_PROVIDERS.includes(v.provider as BrokerProvider) &&
        hash(v.binding) &&
        hash(v.profile_revision) &&
        ["PAPER", "LIVE"].includes(String(v.environment)))
  );
}

export function executionFailure(code: string) {
  if (/legacy_paper|selected_broker_route_active/.test(code))
    return "brokerLegacyConflict";
  if (/revoke_before|reconcile_before|active_plan/.test(code))
    return "brokerSwitchExposure";
  if (/conflict|configuration_changed|not_selected|deselect_before/.test(code))
    return "brokerRouteConflict";
  if (/identity|permission|initial_account|preview/.test(code))
    return "brokerAuthorizationEvidenceMissing";
  if (/runtime_must_be_stopped/.test(code)) return "executionStopFirst";
  return "brokerActionUnconfirmed";
}
