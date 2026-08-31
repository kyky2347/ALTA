import fs from "node:fs";

const LOCAL_ONLY_SETTINGS = [
  "features.apps=false",
  "features.remote_plugin=false",
  "analytics.enabled=false",
];
const UNAUTHENTICATED_SETTINGS = ['cli_auth_credentials_store="ephemeral"'];

function jwtExpiry(token) {
  try {
    const [, payload] = token.split(".");
    const claims = JSON.parse(Buffer.from(payload, "base64url").toString());
    return Number.isFinite(claims.exp) ? claims.exp * 1000 : null;
  } catch {
    return null;
  }
}

function authState(authFile, now, minimumValidityMs) {
  let auth;
  try {
    auth = JSON.parse(fs.readFileSync(authFile, "utf8"));
  } catch {
    return { usable: false, reason: "missing or unreadable auth" };
  }
  if (
    typeof auth.OPENAI_API_KEY === "string" && // pragma: allowlist secret
    auth.OPENAI_API_KEY.trim()
  )
    return { usable: true, reason: "API key auth" };
  const token = auth.tokens?.access_token;
  if (typeof token !== "string" || !token)
    return { usable: false, reason: "missing access token" };
  const expiresAt = jwtExpiry(token);
  if (!expiresAt) return { usable: false, reason: "unverifiable access token" };
  if (expiresAt <= now + minimumValidityMs)
    return { usable: false, reason: "expired access token" };
  return { usable: true, reason: "fresh access token" };
}

function normalizedMode(value) {
  const mode = String(value ?? "auto")
    .trim()
    .toLowerCase();
  if (["1", "true", "on"].includes(mode)) return "enabled";
  if (["0", "false", "off"].includes(mode)) return "disabled";
  if (mode === "auto") return mode;
  throw new Error("ALTA_THIRD_PARTY_OPENAI_SERVICES must be auto, 1, or 0");
}

export function thirdPartyOpenAiServicePolicy(
  authFile,
  {
    mode = process.env.ALTA_THIRD_PARTY_OPENAI_SERVICES,
    now = Date.now(),
    minimumValidityMs = 60_000,
  } = {},
) {
  const selected = normalizedMode(mode);
  const state = authState(authFile, now, minimumValidityMs);
  const enabled =
    selected === "enabled" || (selected === "auto" && state.usable);
  return {
    enabled,
    reason:
      selected === "auto"
        ? state.reason
        : `${selected} by ALTA_THIRD_PARTY_OPENAI_SERVICES`,
    args: [
      ...LOCAL_ONLY_SETTINGS,
      ...(enabled ? [] : UNAUTHENTICATED_SETTINGS),
    ].flatMap((setting) => ["-c", setting]),
  };
}
