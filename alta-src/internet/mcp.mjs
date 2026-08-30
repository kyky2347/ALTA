import {
  executeInternetTool,
  internetPluginIds,
  internetToolDefinitions,
  internetToolNames,
} from "./plugins/registry.mjs";

const MODERN_PROTOCOL = "2026-07-28";
const LEGACY_PROTOCOL = "2025-06-18";
// Each result must leave room for the frozen input, stable instructions, and
// later tool calls inside the same bounded Scout turn. Research packs put
// fetched primary-source text first so this compact preview stays useful.
const MAX_TOOL_RESULT_BYTES = 3_000;
const MAX_TOOL_ERROR_BYTES = 900;
const TRUNCATION_NOTICE =
  "\n...[ALTA truncated this result; narrow the request or fetch sources individually]";
const SERVER_INSTRUCTIONS =
  "Use file read for bounded workspace pages; social search, news search, finance data (including authenticated Finnhub company intelligence when configured), and academic search for public evidence; and general search/research or archive/feed/sitemap for broader discovery. Work in stages: locate an anomaly, inspect the strongest source, verify it through an orthogonal channel, check price or expectations, and test the best rival explanation. TradingView navigation only builds display links: never pass its URLs to fetch, batch-fetch, crawl, research, sitemap, feed, social-read, or archive tools. Prefer primary sources. All tools are read-only and bounded.";

function response(id, result) {
  return { jsonrpc: "2.0", id, result };
}

function error(id, code, message, data) {
  return {
    jsonrpc: "2.0",
    id: id ?? null,
    error: { code, message, ...(data ? { data } : {}) },
  };
}

function toolResult(value) {
  const serialized = JSON.stringify(value, null, 2);
  const originalBytes = Buffer.byteLength(serialized);
  const truncated = originalBytes > MAX_TOOL_RESULT_BYTES;
  const text = truncated
    ? `${utf8Prefix(serialized, MAX_TOOL_RESULT_BYTES - Buffer.byteLength(TRUNCATION_NOTICE))}${TRUNCATION_NOTICE}`
    : serialized;
  return {
    resultType: "complete",
    content: [{ type: "text", text }],
    structuredContent: truncated
      ? { truncated: true, original_bytes: originalBytes }
      : value,
  };
}

function toolError(cause) {
  const originalCode = cause?.code ?? "alta_web_error";
  let code =
    typeof originalCode === "string" ||
    (typeof originalCode === "number" && Number.isFinite(originalCode))
      ? originalCode
      : "alta_web_error";
  const rawMessage = String(cause?.message ?? cause);
  const build = (message) => ({
    resultType: "complete",
    isError: true,
    content: [{ type: "text", text: message }],
    structuredContent: { error: { code, message } },
  });
  if (Buffer.byteLength(JSON.stringify(build(""))) > MAX_TOOL_ERROR_BYTES)
    code = "alta_web_error";
  let low = 0;
  let high = rawMessage.length;
  let value = build("");
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    const candidate = build(rawMessage.slice(0, middle));
    if (Buffer.byteLength(JSON.stringify(candidate)) <= MAX_TOOL_ERROR_BYTES) {
      low = middle;
      value = candidate;
    } else high = middle - 1;
  }
  return low === 0 ? value : build(rawMessage.slice(0, low));
}

function utf8Prefix(value, maximumBytes) {
  let low = 0;
  let high = value.length;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (Buffer.byteLength(value.slice(0, middle)) <= maximumBytes) low = middle;
    else high = middle - 1;
  }
  return value.slice(0, low);
}

export async function handleMcpMessage(service, message, options = {}) {
  if (
    !message ||
    message.jsonrpc !== "2.0" ||
    typeof message.method !== "string"
  ) {
    return error(message?.id, -32600, "Invalid JSON-RPC request");
  }
  if (message.method === "server/discover") {
    return response(message.id, {
      resultType: "complete",
      supportedVersions: [MODERN_PROTOCOL],
      capabilities: { tools: {} },
      _meta: {
        "io.modelcontextprotocol/serverInfo": {
          name: "alta-internet",
          version: "3.5.0",
        },
        "alta/pluginIds": internetPluginIds(),
      },
      ttlMs: 0,
      cacheScope: "private",
    });
  }
  if (message.method === "initialize") {
    return response(message.id, {
      protocolVersion:
        message.params?.protocolVersion === MODERN_PROTOCOL
          ? MODERN_PROTOCOL
          : LEGACY_PROTOCOL,
      capabilities: { tools: {} },
      serverInfo: { name: "alta-internet", version: "3.5.0" },
      instructions: SERVER_INSTRUCTIONS,
    });
  }
  if (message.method === "notifications/initialized") return null;
  if (message.method === "ping") return response(message.id, {});
  if (message.method === "tools/list") {
    return response(message.id, {
      resultType: "complete",
      tools: internetToolDefinitions(),
      _meta: { "alta/pluginIds": internetPluginIds() },
    });
  }
  if (message.method === "tools/call") {
    try {
      const value = await executeInternetTool(
        service,
        message.params?.name,
        message.params?.arguments ?? {},
        options,
      );
      return response(message.id, toolResult(value));
    } catch (cause) {
      return response(message.id, toolError(cause));
    }
  }
  return error(message.id, -32601, `Method not found: ${message.method}`);
}

export { internetToolNames };
