import path from "node:path";
import { retryDelayMs } from "./retry-policy.mjs";
import {
  externalCredentialRoot,
  findCredentialFile,
  readCredentialText,
} from "./credential-files.mjs";

export const PROVIDER_CATALOG_REVISION = 2;
const DEEPSEEK_CONTEXT_WINDOW = 1_000_000;

export const PROVIDERS = Object.freeze({
  deepseek: {
    label: "DeepSeek",
    envKeys: ["DEEPSEEK_API_KEY"],
    fileHints: ["deepseek", "deeepseek"],
    modelsUrls: ["https://api.deepseek.com/models"],
    inferenceUrl: "https://api.deepseek.com/responses",
    protocol: "responses",
    fallback: [
      {
        id: "deepseek-v4-pro",
        context_window: DEEPSEEK_CONTEXT_WINDOW,
        reasoning: true,
      },
      {
        id: "deepseek-v4-flash",
        context_window: DEEPSEEK_CONTEXT_WINDOW,
        reasoning: true,
      },
      {
        id: "deepseek-v4-flash-vision-exp",
        context_window: DEEPSEEK_CONTEXT_WINDOW,
        reasoning: true,
        input_modalities: ["text", "image"],
      },
    ],
  },
  xai: {
    label: "xAI / Grok",
    envKeys: ["XAI_API_KEY", "GROK_API_KEY"],
    fileHints: ["grok", "xai"],
    modelsUrls: [
      "https://api.x.ai/v1/language-models",
      "https://api.x.ai/v1/models",
    ],
    inferenceUrl: "https://api.x.ai/v1/responses",
    protocol: "responses",
    fallback: [{ id: "grok-4.6", context_window: 500_000, reasoning: true }],
  },
  kimi: {
    label: "Kimi / Moonshot",
    envKeys: ["MOONSHOT_API_KEY", "KIMI_API_KEY"],
    fileHints: ["kimi", "moonshot"],
    modelsUrls: ["https://api.moonshot.cn/v1/models"],
    inferenceUrl: "https://api.moonshot.cn/v1/chat/completions",
    protocol: "chat",
    fallback: [
      { id: "kimi-k3", context_window: 262_144, reasoning: true },
      { id: "kimi-k2.7-code", context_window: 262_144, reasoning: true },
      {
        id: "kimi-k2.7-code-highspeed",
        context_window: 262_144,
        reasoning: true,
      },
      { id: "kimi-k2.6", context_window: 262_144, reasoning: true },
    ],
  },
});

// Codex-facing IDs are intentionally stable and user-readable. The gateway keeps
// xAI as its runtime ID because that is also the credential/discovery key.
export const MODEL_PROVIDER_IDS = Object.freeze({
  deepseek: "deepseek",
  xai: "grok",
  kimi: "kimi",
});

const BASE_OVERRIDES = {
  deepseek: "ALTA_DEEPSEEK_BASE_URL",
  xai: "ALTA_XAI_BASE_URL",
  kimi: "ALTA_KIMI_BASE_URL",
};

function safeBaseUrl(value) {
  const parsed = new URL(value);
  const loopback = ["127.0.0.1", "::1", "localhost"].includes(parsed.hostname);
  if (
    parsed.protocol !== "https:" &&
    !(loopback && process.env.ALTA_ALLOW_INSECURE_LOOPBACK === "1")
  ) {
    throw new Error(
      "Provider base URLs must use HTTPS (except explicit loopback tests)",
    );
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error(
      "Provider base URLs cannot contain credentials, queries, or fragments",
    );
  }
  return parsed.href.replace(/\/+$/, "");
}

export function runtimeProvider(name) {
  const provider = PROVIDERS[name];
  if (!provider) throw new Error(`Unknown provider: ${name}`);
  const override = process.env[BASE_OVERRIDES[name]];
  if (!override) return provider;
  const base = safeBaseUrl(override);
  return {
    ...provider,
    modelsUrls: [`${base}/models`],
    inferenceUrl: `${base}/${provider.protocol === "chat" ? "chat/completions" : "responses"}`,
  };
}

function extractCredential(text, providerName) {
  const patterns =
    providerName === "xai"
      ? [/xai-[A-Za-z0-9_.-]{20,}/g, /\b[A-Za-z0-9_-]{60,}\b/g]
      : [/sk-[A-Za-z0-9_.-]{20,}/g];
  for (const pattern of patterns) {
    const matches = text.match(pattern);
    if (matches?.length) return matches[0];
  }
  return null;
}

export function validateProviderCredential(providerName, value) {
  if (!PROVIDERS[providerName])
    throw new Error(`Unknown provider: ${providerName}`);
  const candidate = String(value ?? "").trim();
  if (
    !candidate ||
    candidate.length > 512 ||
    /[\u0000-\u001f\u007f]/.test(candidate) ||
    extractCredential(candidate, providerName) !== candidate
  )
    throw new Error(
      `Invalid ${PROVIDERS[providerName].label} credential format`,
    );
  return candidate;
}

export function loadCredentials(env = process.env) {
  const root = externalCredentialRoot(env);
  const credentials = {};
  const sources = {};
  for (const [name, provider] of Object.entries(PROVIDERS)) {
    const envName = provider.envKeys.find((key) => env[key]);
    if (envName) {
      credentials[name] = validateProviderCredential(name, env[envName]);
      sources[name] = `environment (${envName})`;
      continue;
    }
    const file = findCredentialFile(root, "llm", provider.fileHints);
    if (!file) continue;
    const credential = extractCredential(readCredentialText(file), name);
    if (!credential)
      throw new Error(
        `External ${provider.label} credential file ${path.basename(file)} has no valid credential`,
      );
    credentials[name] = validateProviderCredential(name, credential);
    sources[name] = `external credential file (${path.basename(file)})`;
  }
  return { credentials, sources };
}

function normalizedModels(payload) {
  const values = payload?.data ?? payload?.models ?? payload?.items ?? [];
  return Array.isArray(values) ? values : [];
}

export function providerModelCapabilities(providerName, id, value = {}) {
  const reported = value.input_modalities ?? value.modalities?.input;
  const inputModalities = new Set(["text"]);
  if (Array.isArray(reported)) {
    for (const modality of reported) {
      const normalized = String(modality).toLowerCase();
      if (normalized === "image") inputModalities.add(normalized);
    }
  } else {
    if (
      value.image === true ||
      value.supports_image_input === true ||
      value.supports_vision === true
    )
      inputModalities.add("image");
  }
  const currentKimiVision = /^kimi-(?:k3|k2\.(?:6|7))(?:$|-)/i.test(id);
  const currentXaiVision = /^grok-4\.(?:5|6)(?:$|-)/i.test(id);
  const currentDeepSeekVision = /^deepseek-v4-flash-vision-exp$/i.test(id);
  if (
    !Array.isArray(reported) &&
    (currentKimiVision || currentXaiVision || currentDeepSeekVision)
  )
    inputModalities.add("image");
  return {
    inputModalities: [...inputModalities],
    video:
      inputModalities.has("image") &&
      (value.video === true ||
        value.supports_video_input === true ||
        (providerName === "kimi" && currentKimiVision)),
  };
}

function normalizeModel(providerName, value) {
  const id = value?.id ?? value?.model ?? value?.name;
  if (typeof id !== "string" || !id.trim()) return null;
  const normalizedId = id.trim();
  const capabilities = providerModelCapabilities(
    providerName,
    normalizedId,
    value,
  );
  const defaultContext =
    providerName === "deepseek"
      ? DEEPSEEK_CONTEXT_WINDOW
      : providerName === "xai" && id === "grok-4.6"
        ? 500_000
        : 262_144;
  const inferredReasoning =
    /reason|thinking|code|k3|multi-agent|grok-4|deepseek-v4/i.test(id) &&
    !/non-reasoning|grok-build/i.test(id);
  return {
    id: normalizedId,
    context_window: Number(
      value.context_window ??
        value.context_length ??
        value.max_context_length ??
        defaultContext,
    ),
    reasoning: Boolean(
      value.supports_reasoning ?? value.reasoning ?? inferredReasoning,
    ),
    input_modalities: capabilities.inputModalities,
    image: capabilities.inputModalities.includes("image"),
    audio: capabilities.inputModalities.includes("audio"),
    video: capabilities.video,
    provider: providerName,
  };
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function fetchJsonWithRetry(url, options = {}, policy = {}) {
  const attempts = policy.attempts ?? 5;
  const timeoutMs = policy.timeoutMs ?? 30_000;
  let lastError;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const controller = new AbortController();
    const timer = setTimeout(
      () => controller.abort(new Error("request timed out")),
      timeoutMs,
    );
    try {
      const response = await (policy.fetchImpl ?? fetch)(url, {
        ...options,
        signal: controller.signal,
      });
      const text = await response.text();
      if (response.ok) return JSON.parse(text);
      const error = new Error(
        `HTTP ${response.status}: ${redact(text).slice(0, 500)}`,
      );
      error.status = response.status;
      error.retryAfter = response.headers.get("retry-after");
      throw error;
    } catch (error) {
      lastError = error;
      if (
        attempt + 1 >= attempts ||
        (error.status &&
          ![408, 409, 425, 429, 500, 502, 503, 504].includes(error.status))
      ) {
        throw error;
      }
      await (policy.sleepImpl ?? wait)(
        retryDelayMs(attempt, error.retryAfter, {
          maximumMs: 8_000,
          jitterMs: 250,
          now: policy.now ?? Date.now,
          random: policy.random ?? Math.random,
        }),
      );
    } finally {
      clearTimeout(timer);
    }
  }
  throw lastError;
}

export async function discoverProviderModels(
  providerName,
  credential,
  policy = {},
) {
  const provider = runtimeProvider(providerName);
  let lastError;
  for (const url of provider.modelsUrls) {
    try {
      const payload = await fetchJsonWithRetry(
        url,
        {
          headers: {
            Authorization: `Bearer ${credential}`,
            Accept: "application/json",
          },
        },
        policy,
      );
      const models = normalizedModels(payload)
        .map((value) => normalizeModel(providerName, value))
        .filter(Boolean);
      if (models.length) return models;
    } catch (error) {
      lastError = error;
    }
  }
  throw (
    lastError ?? new Error(`${provider.label} returned an empty model catalog`)
  );
}

export function fallbackModels(providerName) {
  return runtimeProvider(providerName).fallback.map((model) =>
    normalizeModel(providerName, model),
  );
}

export function hydrateProviderModels(models = []) {
  return models
    .map((model) => normalizeModel(model.provider, model))
    .filter(Boolean);
}

export function redact(value, secrets = []) {
  let text = String(value ?? "");
  for (const secret of secrets.filter(Boolean))
    text = text.replaceAll(secret, "[REDACTED]");
  return text
    .replace(/(?:sk|xai)-[A-Za-z0-9_.-]{12,}/g, "[REDACTED]")
    .replace(/Bearer\s+[A-Za-z0-9_.-]+/gi, "Bearer [REDACTED]");
}
