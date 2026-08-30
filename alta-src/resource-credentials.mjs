import path from "node:path";
import {
  externalCredentialRoot,
  findCredentialFile,
  readCredentialText,
} from "./credential-files.mjs";

export const RESOURCE_CREDENTIALS = Object.freeze({
  MASSIVE_API_KEY: {
    directoryName: "resources",
    hints: ["massive", "polygon"],
    patterns: [
      /[?&]key=([A-Za-z0-9_-]{20,128})/i,
      /\b(?:massive|polygon)[^\r\n]{0,40}\b([A-Za-z0-9_-]{20,128})\b/i,
    ],
  },
  FINLIGHT_API_KEY: {
    directoryName: "resources",
    hints: ["finlight"],
    patterns: [/\b(sk-[A-Za-z0-9_-]{20,128})\b/i],
  },
  FINNHUB_API_KEY: {
    directoryName: "resources",
    hints: ["finnhub"],
    patterns: [
      /[?&]token=([A-Za-z0-9_-]{16,128})/i,
      /\bfinnhub[^\r\n]{0,48}\b([A-Za-z0-9_-]{16,128})\b/i,
    ],
  },
  BRAVE_SEARCH_API_KEY: {
    directoryName: "tools",
    hints: ["brave"],
    patterns: [/\b(BSA[A-Za-z0-9_-]{20,128})\b/],
  },
  JINA_API_KEY: {
    directoryName: "tools",
    hints: ["jina"],
    patterns: [/\b(jina_[A-Za-z0-9_-]{20,128})\b/i],
  },
  OPENALEX_API_KEY: {
    directoryName: "tools",
    hints: ["openalex"],
    patterns: [/\b(openalex[A-Za-z0-9_-]{20,128})\b/i],
  },
});

export const TOOL_CREDENTIAL_KEYS = Object.freeze([
  "BRAVE_SEARCH_API_KEY",
  "JINA_API_KEY",
  "OPENALEX_API_KEY",
  "FINNHUB_API_KEY",
]);

function genericCandidate(text) {
  const candidates = text.match(/\b[A-Za-z0-9_-]{24,128}\b/g) ?? [];
  return candidates.find(
    (value) =>
      /[A-Za-z]/.test(value) &&
      /\d/.test(value) &&
      !/^(?:https?|websocket|authorization)/i.test(value),
  );
}

function extractCredential(text, patterns) {
  for (const pattern of patterns) {
    const value = text.match(pattern)?.[1];
    if (value) return value;
  }
  return genericCandidate(text) ?? null;
}

export function validateResourceCredential(environmentKey, value) {
  const specification = RESOURCE_CREDENTIALS[environmentKey];
  if (!specification)
    throw new Error(`Unknown ALTA resource credential: ${environmentKey}`);
  const candidate = String(value ?? "").trim();
  if (
    !candidate ||
    candidate.length > 512 ||
    /[\u0000-\u001f\u007f]/.test(candidate)
  )
    throw new Error(`Invalid ${environmentKey} credential`);
  const extracted = extractCredential(candidate, specification.patterns);
  if (extracted !== candidate)
    throw new Error(`Invalid ${environmentKey} credential format`);
  return candidate;
}

export function loadResourceCredentials(
  env = process.env,
  environmentKeys = Object.keys(RESOURCE_CREDENTIALS),
) {
  const root = externalCredentialRoot(env);
  const values = {};
  const sources = {};
  for (const environmentKey of environmentKeys) {
    const specification = RESOURCE_CREDENTIALS[environmentKey];
    if (!specification)
      throw new Error(`Unknown ALTA resource credential: ${environmentKey}`);
    if (env[environmentKey]) {
      values[environmentKey] = validateResourceCredential(
        environmentKey,
        env[environmentKey],
      );
      sources[environmentKey] = `environment (${environmentKey})`;
      continue;
    }
    const file = findCredentialFile(
      root,
      specification.directoryName,
      specification.hints,
    );
    if (!file) continue;
    const credential = extractCredential(
      readCredentialText(file),
      specification.patterns,
    );
    if (!credential)
      throw new Error(
        `External ${environmentKey} credential file ${path.basename(file)} has no valid credential`,
      );
    values[environmentKey] = validateResourceCredential(
      environmentKey,
      credential,
    );
    sources[environmentKey] =
      `external credential file (${path.basename(file)})`;
  }
  return { values, sources };
}
