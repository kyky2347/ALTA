import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import {
  externalCredentialRoot,
  findCredentialFile,
  readCredentialText,
  replaceCredentialFile,
} from "./credential-files.mjs";
import {
  loadCredentials,
  PROVIDERS,
  validateProviderCredential,
} from "./providers.mjs";
import {
  loadResourceCredentials,
  RESOURCE_CREDENTIALS,
  validateResourceCredential,
} from "./resource-credentials.mjs";

const RESOURCE_SLOTS = Object.freeze({
  massive: "MASSIVE_API_KEY",
  finlight: "FINLIGHT_API_KEY",
  finnhub: "FINNHUB_API_KEY",
  brave: "BRAVE_SEARCH_API_KEY",
  jina: "JINA_API_KEY",
  openalex: "OPENALEX_API_KEY",
});

const SLOT_METADATA = Object.freeze({
  deepseek: {
    label: "DeepSeek",
    category: "models",
    purpose: "Primary agent inference and research",
    credentialRequirement: "required",
  },
  xai: {
    label: "xAI / Grok",
    category: "models",
    purpose: "Independent debate and web-aware research",
    credentialRequirement: "required",
  },
  kimi: {
    label: "Kimi / Moonshot",
    category: "models",
    purpose: "Independent analysis and long-context research",
    credentialRequirement: "required",
  },
  massive: {
    label: "Massive",
    category: "market_data",
    purpose: "US equity and option market data",
    credentialRequirement: "required",
  },
  finlight: {
    label: "Finlight",
    category: "news",
    purpose: "Normalized market news",
    credentialRequirement: "required",
  },
  finnhub: {
    label: "Finnhub",
    category: "market_data",
    purpose: "Company events, fundamentals, peers, and insider activity",
    credentialRequirement: "optional",
  },
  brave: {
    label: "Brave Search",
    category: "research",
    purpose: "Open-web search",
    credentialRequirement: "optional",
  },
  jina: {
    label: "Jina Reader",
    category: "research",
    purpose: "Readable web content extraction",
    credentialRequirement: "optional",
    availableWithoutCredential: true,
  },
  openalex: {
    label: "OpenAlex",
    category: "research",
    purpose: "Academic and research discovery",
    credentialRequirement: "optional",
    availableWithoutCredential: true,
  },
});

const BUILT_IN_PROVIDER_NETWORK = Object.freeze([
  {
    category: "market_and_regulatory",
    providers: [
      "Nasdaq",
      "SEC EDGAR",
      "FRED",
      "BLS",
      "New York Fed",
      "U.S. Treasury",
      "World Bank",
      "IMF",
      "OECD",
      "ECB",
      "Bank of Canada",
      "Eurostat",
      "FDIC",
      "CFTC",
      "Coinbase",
      "Kraken",
    ],
  },
  {
    category: "news_and_discovery",
    providers: [
      "GDELT",
      "Google News RSS",
      "Yahoo Finance RSS",
      "Nasdaq News",
      "GlobeNewswire",
      "Benzinga RSS",
      "Investing.com RSS",
    ],
  },
  {
    category: "research_and_social",
    providers: [
      "Crossref",
      "arXiv",
      "Reddit",
      "Hacker News",
      "Bluesky",
      "Mastodon",
      "Lemmy",
      "Stack Exchange",
      "PeerTube",
    ],
  },
]);

export const CREDENTIAL_SLOT_IDS = Object.freeze([
  ...Object.keys(PROVIDERS),
  ...Object.keys(RESOURCE_SLOTS),
]);

export function canonicalCredentialSlot(value) {
  const normalized = String(value ?? "")
    .trim()
    .toLowerCase();
  const slot = normalized === "grok" ? "xai" : normalized;
  if (!CREDENTIAL_SLOT_IDS.includes(slot))
    throw new Error(
      `Unknown credential slot "${value}"; choose ${CREDENTIAL_SLOT_IDS.join(", ")}`,
    );
  return slot;
}

function slotDefinition(slot) {
  if (PROVIDERS[slot]) {
    const provider = PROVIDERS[slot];
    return {
      directoryName: "llm",
      environmentKeys: provider.envKeys,
      hints: provider.fileHints,
      canonicalName: `${slot}.key`,
      validate: (value) => validateProviderCredential(slot, value),
    };
  }
  const environmentKey = RESOURCE_SLOTS[slot];
  const resource = RESOURCE_CREDENTIALS[environmentKey];
  return {
    directoryName: resource.directoryName,
    environmentKeys: [environmentKey],
    hints: resource.hints,
    canonicalName: `${slot}.key`,
    validate: (value) => validateResourceCredential(environmentKey, value),
  };
}

function loadedValues(env) {
  const providers = loadCredentials(env);
  const resources = loadResourceCredentials(env);
  return {
    values: {
      ...providers.credentials,
      ...Object.fromEntries(
        Object.entries(RESOURCE_SLOTS).flatMap(([slot, environmentKey]) =>
          resources.values[environmentKey]
            ? [[slot, resources.values[environmentKey]]]
            : [],
        ),
      ),
    },
    sources: {
      ...providers.sources,
      ...Object.fromEntries(
        Object.entries(RESOURCE_SLOTS).flatMap(([slot, environmentKey]) =>
          resources.sources[environmentKey]
            ? [[slot, resources.sources[environmentKey]]]
            : [],
        ),
      ),
    },
  };
}

function revision(values, tradingFingerprint = "") {
  const hash = createHash("sha256");
  for (const slot of CREDENTIAL_SLOT_IDS) {
    hash.update(slot);
    hash.update("\0");
    hash.update(values[slot] ?? "");
    hash.update("\0");
  }
  hash.update("tiger-paper\0");
  hash.update(tradingFingerprint);
  return hash.digest("hex").slice(0, 16);
}

function fingerprint(value) {
  if (value === undefined) return null;
  return createHash("sha256").update(value).digest("hex").slice(0, 12);
}

function sourceKind(source) {
  if (source?.startsWith("environment (")) return "environment";
  if (source?.startsWith("external credential file (")) return "external";
  return "missing";
}

function tigerPaperInventory(root, env) {
  let file = null;
  let source = "missing";
  let sourceKindValue = "missing";
  if (env.ALTA_TIGER_CONFIG_PATH) {
    file = path.resolve(env.ALTA_TIGER_CONFIG_PATH);
    source = "environment (ALTA_TIGER_CONFIG_PATH)";
    sourceKindValue = "environment";
  } else {
    file = findCredentialFile(root, "broker", ["tiger"]);
    if (file) {
      source = `external credential file (${path.basename(file)})`;
      sourceKindValue = "external";
    }
  }
  if (!file || !fs.existsSync(file))
    return {
      provider: "Tiger Trade",
      mode: "paper_only",
      configured: false,
      editable: false,
      source,
      sourceKind: sourceKindValue,
      fingerprint: null,
      status: "not_configured_capital_disabled",
    };
  const text = readCredentialText(file);
  const hasAccount = /(?:^|\n)\s*account\s*=/i.test(text);
  const hasTigerId = /(?:^|\n)\s*tiger_id\s*=/i.test(text);
  const hasPrivateKey = /(?:^|\n)\s*private_key(?:_pk(?:1|8))?\s*=/i.test(text);
  const configured = hasAccount && hasTigerId && hasPrivateKey;
  return {
    provider: "Tiger Trade",
    mode: "paper_only",
    configured,
    editable: false,
    source,
    sourceKind: sourceKindValue,
    fingerprint: fingerprint(text),
    status: configured
      ? "configured_external_capital_disabled"
      : "invalid_external_config",
  };
}

export function credentialInventory(env = process.env) {
  const root = externalCredentialRoot(env);
  const loaded = loadedValues(env);
  const trading = tigerPaperInventory(root, env);
  return {
    root,
    revision: revision(loaded.values, trading.fingerprint ?? ""),
    configuredSlots: CREDENTIAL_SLOT_IDS.filter(
      (slot) => loaded.values[slot] !== undefined,
    ),
    slots: CREDENTIAL_SLOT_IDS.map((slot) => ({
      slot,
      ...SLOT_METADATA[slot],
      configured: loaded.values[slot] !== undefined,
      operational:
        loaded.values[slot] !== undefined ||
        SLOT_METADATA[slot].availableWithoutCredential === true,
      source: loaded.sources[slot] ?? "missing",
      sourceKind: sourceKind(loaded.sources[slot]),
      editable: sourceKind(loaded.sources[slot]) !== "environment",
      fingerprint: fingerprint(loaded.values[slot]),
    })),
    providerNetwork: BUILT_IN_PROVIDER_NETWORK,
    trading,
  };
}

export function replaceCredential(slotValue, secret, env = process.env) {
  const slot = canonicalCredentialSlot(slotValue);
  const definition = slotDefinition(slot);
  const environmentKey = definition.environmentKeys.find((key) => env[key]);
  if (environmentKey)
    throw new Error(
      `${slot} is supplied by ${environmentKey}; unset that environment variable before replacing its external file`,
    );
  const value = definition.validate(secret);
  const root = externalCredentialRoot(env);
  const replacement = replaceCredentialFile({
    root,
    directoryName: definition.directoryName,
    hints: definition.hints,
    canonicalName: definition.canonicalName,
    value,
  });
  try {
    const loaded = loadedValues(env);
    if (loaded.values[slot] !== value)
      throw new Error(`ALTA could not verify the replaced ${slot} credential`);
    return {
      slot,
      source: loaded.sources[slot],
      fileName: path.basename(replacement.file),
      revision: revision(loaded.values),
      restore: replacement.restore,
    };
  } catch (error) {
    replacement.restore();
    throw error;
  }
}
