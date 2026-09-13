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
  snapshot?: BrokerAccountSnapshot;
};
export type BrokerAccountSnapshot = {
  verified_at: string;
  account_verified: boolean;
  environment_verified: boolean;
  trading_permitted: boolean;
  order_preview_required?: boolean;
  currency: string;
  equity: string;
  cash: string;
  buying_power: string;
  positions: Array<{
    symbol: string;
    quantity: string;
    market_value: string | null;
    currency: string;
  }>;
  orders: Array<{
    order_id: string;
    symbol: string;
    side: "BUY" | "SELL";
    quantity: string;
    filled: string;
    state: "working" | "unknown" | "filled" | "cancelled" | "rejected";
  }>;
};

export const BROKER_CHECKS = [
  "fresh_account",
  "account_identity",
  "environment_identity",
  "trade_permission",
  "empty_account",
  "clear_ledger",
  "runner_integration",
  "account_acceptance",
] as const;
export type BrokerAccountState = BrokerVerification & {
  environment: "PAPER" | "LIVE";
  revision: string;
  binding: string;
  authority: "off" | "entries" | "close_only";
  orders?: Array<{
    client_id: string;
    symbol: string;
    side: "BUY" | "SELL";
    quantity: string;
    filled: string;
    state:
      | "prepared"
      | "working"
      | "unknown"
      | "filled"
      | "cancelled"
      | "rejected";
  }>;
  verification: {
    status:
      | "not_checked"
      | "configuration_changed"
      | "failed"
      | "verified"
      | "stale"
      | "unavailable";
    fresh: boolean;
    snapshot: BrokerAccountSnapshot | null;
  };
  authorization_review: {
    eligible: boolean;
    checks: Record<(typeof BROKER_CHECKS)[number], boolean>;
    provider: string;
    environment: "PAPER" | "LIVE";
    binding: string;
    revision: string;
    limits: {
      max_order_notional: string;
      max_gross_notional: string;
      max_quote_age_seconds: number;
    };
  };
};

const decimal = (value: unknown) =>
  typeof value === "string" &&
  /^-?\d+(\.\d+)?([eE][+-]?\d+)?$/.test(value) &&
  Number.isFinite(Number(value));
const object = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

export function validBrokerAccountState(
  value: unknown,
): value is BrokerAccountState {
  if (
    !object(value) ||
    !object(value.verification) ||
    !object(value.authorization_review)
  )
    return false;
  const v = value.verification;
  const r = value.authorization_review;
  return (
    typeof value.provider === "string" &&
    ["tiger", "alpaca", "ibkr", "futu", "longport", "schwab"].includes(
      value.provider,
    ) &&
    ["PAPER", "LIVE"].includes(String(value.environment)) &&
    /^[a-f0-9]{64}$/.test(String(value.revision)) &&
    /^[a-f0-9]{64}$/.test(String(value.binding)) &&
    ["off", "entries", "close_only"].includes(String(value.authority)) &&
    (value.orders === undefined ||
      (Array.isArray(value.orders) &&
        value.orders.length <= 100 &&
        value.orders.every(
          (o) =>
            object(o) &&
            /^alta-[a-f0-9]{32}$/.test(String(o.client_id)) &&
            typeof o.symbol === "string" &&
            o.symbol.length <= 40 &&
            ["BUY", "SELL"].includes(String(o.side)) &&
            decimal(o.quantity) &&
            decimal(o.filled) &&
            [
              "prepared",
              "unknown",
              "working",
              "filled",
              "cancelled",
              "rejected",
            ].includes(String(o.state)),
        ))) &&
    [
      "not_checked",
      "configuration_changed",
      "failed",
      "verified",
      "stale",
      "unavailable",
    ].includes(String(v.status)) &&
    typeof v.fresh === "boolean" &&
    (v.snapshot === null ||
      validBrokerVerification({
        provider: value.provider,
        snapshot: v.snapshot,
      })) &&
    (!v.fresh || (v.status === "verified" && v.snapshot !== null)) &&
    typeof r.eligible === "boolean" &&
    r.provider === value.provider &&
    r.environment === value.environment &&
    r.binding === value.binding &&
    r.revision === value.revision &&
    object(r.checks) &&
    BROKER_CHECKS.every(
      (k) => typeof (r.checks as Record<string, unknown>)[k] === "boolean",
    ) &&
    (!r.eligible ||
      (v.fresh === true &&
        BROKER_CHECKS.every(
          (k) => (r.checks as Record<string, unknown>)[k] === true,
        ))) &&
    object(r.limits) &&
    decimal(r.limits.max_order_notional) &&
    decimal(r.limits.max_gross_notional) &&
    typeof r.limits.max_quote_age_seconds === "number" &&
    Number.isInteger(r.limits.max_quote_age_seconds) &&
    r.limits.max_quote_age_seconds >= 1 &&
    r.limits.max_quote_age_seconds <= 30
  );
}

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
  if (/deselect_before|revoke_before|ledger_migration|fresh_flat/.test(code))
    return "brokerEnvironmentBound";
  if (/conflict|credential_change|account_profile/.test(code))
    return "brokerConnectionConflict";
  if (/invalid|mismatch/.test(code)) return "brokerFieldsInvalid";
  if (/timed_out|timeout/.test(code)) return "brokerConnectionTimeout";
  if (/authentication/.test(code)) return "brokerAuthenticationRequired";
  if (/rate_limited/.test(code)) return "brokerRateLimited";
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
    decimal(s.equity) &&
    decimal(s.cash) &&
    decimal(s.buying_power) &&
    Array.isArray(s.positions) &&
    s.positions.length <= 1000 &&
    s.positions.every(
      (p) =>
        object(p) &&
        typeof p.symbol === "string" &&
        p.symbol.length <= 40 &&
        decimal(p.quantity) &&
        (p.market_value === null || decimal(p.market_value)) &&
        typeof p.currency === "string" &&
        /^[A-Z]{3}$/.test(p.currency),
    ) &&
    Array.isArray(s.orders) &&
    s.orders.length <= 2000 &&
    s.orders.every(
      (o) =>
        object(o) &&
        typeof o.order_id === "string" &&
        /^[a-f0-9]{16}$/.test(o.order_id) &&
        typeof o.symbol === "string" &&
        o.symbol.length <= 40 &&
        (o.side === "BUY" || o.side === "SELL") &&
        decimal(o.quantity) &&
        decimal(o.filled) &&
        typeof o.state === "string" &&
        ["working", "unknown", "filled", "cancelled", "rejected"].includes(
          o.state,
        ),
    )
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
