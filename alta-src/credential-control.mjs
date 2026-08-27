import { createHash } from "node:crypto";
import path from "node:path";
import process from "node:process";
import {
  externalCredentialRoot,
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
  brave: "BRAVE_SEARCH_API_KEY",
  jina: "JINA_API_KEY",
  openalex: "OPENALEX_API_KEY",
});

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

function revision(values) {
  const hash = createHash("sha256");
  for (const slot of CREDENTIAL_SLOT_IDS) {
    hash.update(slot);
    hash.update("\0");
    hash.update(values[slot] ?? "");
    hash.update("\0");
  }
  return hash.digest("hex").slice(0, 16);
}

export function credentialInventory(env = process.env) {
  const root = externalCredentialRoot(env);
  const loaded = loadedValues(env);
  return {
    root,
    revision: revision(loaded.values),
    configuredSlots: CREDENTIAL_SLOT_IDS.filter(
      (slot) => loaded.values[slot] !== undefined,
    ),
    slots: CREDENTIAL_SLOT_IDS.map((slot) => ({
      slot,
      configured: loaded.values[slot] !== undefined,
      source: loaded.sources[slot] ?? "missing",
    })),
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
