export const BROKER_AUTH = [
  "rsa",
  "key_pair",
  "tws_gateway",
  "opend",
  "account_token",
  "oauth",
] as const;
export const BROKER_FIELDS = [
  "tiger_id",
  "private_key",
  "api_key",
  "api_secret",
  "port",
  "client_id",
  "security_firm",
  "trade_password",
  "app_key",
  "app_secret",
  "access_token",
  "account_hash",
] as const;
export type BrokerConnection = {
  provider: string;
  name: string;
  environments: Array<"PAPER" | "LIVE">;
  fields: (typeof BROKER_FIELDS)[number][];
  authentication: (typeof BROKER_AUTH)[number];
  proof: string;
  docs: string;
  configured: boolean;
  revision: string;
  environment?: "PAPER" | "LIVE";
  binding?: string;
  profile_error?: "broker_profile_unreadable";
  autonomous_execution: false;
  acceptance: "not_verified";
};
export type BrokerConnectionRequest =
  | { action: "verify"; provider: string }
  | {
      action: "save";
      revision: string;
      profile: {
        provider: string;
        environment: "PAPER" | "LIVE";
        account: string;
        credentials: Record<string, string>;
      };
    };
export type BrokerVerification = {
  provider: string;
  snapshot?: {
    verified_at: string;
    account_verified: boolean;
    environment_verified: boolean;
    trading_permitted: boolean;
    currency: string;
    positions: unknown[];
    orders: unknown[];
  };
};

export function brokerCredentialFields(
  broker: BrokerConnection | undefined,
  environment: "PAPER" | "LIVE",
) {
  return (broker?.fields ?? []).filter(
    (field) =>
      !(
        broker?.provider === "futu" &&
        environment === "PAPER" &&
        field === "trade_password"
      ),
  );
}

export function brokerFieldKind(
  field: string,
): "secret" | "number" | "firm" | "key" {
  if (field === "port" || field === "client_id") return "number";
  if (field === "security_firm") return "firm";
  if (field === "private_key") return "key";
  return "secret";
}

export function brokerConnectionError(code: string) {
  if (code === "broker_dependencies_not_installed")
    return "brokerInstallRequired";
  if (/conflict|credential_change|account_profile/.test(code))
    return "brokerConnectionConflict";
  if (/invalid|mismatch/.test(code)) return "brokerFieldsInvalid";
  if (/timed_out|timeout/.test(code)) return "brokerConnectionTimeout";
  return "brokerConnectionUnavailable";
}

export function validBrokerVerification(
  value: unknown,
): value is BrokerVerification {
  if (
    !value ||
    typeof value !== "object" ||
    !("provider" in value) ||
    typeof value.provider !== "string" ||
    !("snapshot" in value) ||
    !value.snapshot ||
    typeof value.snapshot !== "object"
  )
    return false;
  const s = value.snapshot as Record<string, unknown>;
  return (
    typeof s.verified_at === "string" &&
    Number.isFinite(Date.parse(s.verified_at)) &&
    typeof s.account_verified === "boolean" &&
    typeof s.environment_verified === "boolean" &&
    typeof s.trading_permitted === "boolean" &&
    typeof s.currency === "string" &&
    Array.isArray(s.positions) &&
    Array.isArray(s.orders)
  );
}

export function validBrokerCatalog(
  value: unknown,
): value is { brokers: BrokerConnection[] } {
  if (
    !value ||
    typeof value !== "object" ||
    !("brokers" in value) ||
    !Array.isArray(value.brokers)
  )
    return false;
  const providers = new Set([
    "tiger",
    "alpaca",
    "ibkr",
    "futu",
    "longport",
    "schwab",
  ]);
  return (
    value.brokers.length === 6 &&
    value.brokers.every((row) => {
      if (!row || !providers.delete(row.provider)) return false;
      return (
        typeof row.name === "string" &&
        safeBrokerDocs(row.docs) &&
        typeof row.configured === "boolean" &&
        typeof row.revision === "string" &&
        BROKER_AUTH.includes(row.authentication) &&
        Array.isArray(row.fields) &&
        row.fields.every((f: unknown) =>
          BROKER_FIELDS.some((known) => known === f),
        ) &&
        Array.isArray(row.environments) &&
        row.environments.length > 0 &&
        row.environments.every((v: unknown) => v === "PAPER" || v === "LIVE") &&
        (row.environment === undefined ||
          row.environments.includes(row.environment)) &&
        (row.profile_error === undefined ||
          row.profile_error === "broker_profile_unreadable") &&
        row.autonomous_execution === false &&
        row.acceptance === "not_verified"
      );
    })
  );
}

function safeBrokerDocs(value: unknown) {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return (
      url.protocol === "https:" &&
      !url.username &&
      !url.password &&
      [
        "docs-en.itigerup.com",
        "docs.alpaca.markets",
        "www.interactivebrokers.com",
        "openapi.futunn.com",
        "open.longbridge.com",
        "developer.schwab.com",
      ].includes(url.hostname)
    );
  } catch {
    return false;
  }
}
