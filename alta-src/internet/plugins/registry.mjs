import { academicPlugin } from "./academic.mjs";
import { corePlugin } from "./core.mjs";
import { discoveryPlugin } from "./discovery.mjs";
import { financePlugin } from "./finance.mjs";
import { filesPlugin } from "./files.mjs";
import { newsPlugin } from "./news.mjs";
import { researchPlugin } from "./research.mjs";
import { socialPlugin } from "./social.mjs";
import { tradingViewPlugin } from "./tradingview.mjs";
import { withDeadline } from "../deadline.mjs";

const PLUGINS = [
  corePlugin,
  researchPlugin,
  discoveryPlugin,
  academicPlugin,
  socialPlugin,
  newsPlugin,
  financePlugin,
  tradingViewPlugin,
  filesPlugin,
];
const TOOLS = new Map();
for (const plugin of PLUGINS) {
  for (const tool of plugin.tools) {
    if (TOOLS.has(tool.definition.name))
      throw new Error(`Duplicate ALTA internet tool: ${tool.definition.name}`);
    TOOLS.set(tool.definition.name, { ...tool, plugin: plugin.id });
  }
}

export function internetToolDefinitions(service) {
  return [...TOOLS.values()].map(({ definition }) => {
    const copy = structuredClone(definition);
    // A configured route is not proof of health, but advertising absent search
    // credentials wastes the Scout's scarce research calls before any retrieval.
    if (service && copy.name.startsWith("alta_web_")) {
      const backend = copy.inputSchema.properties.backend;
      if (backend?.enum) {
        const configured = new Set([
          "auto",
          "federated",
          "public",
          "duckduckgo",
          "bing",
          ...(service.braveKey ? ["brave"] : []),
          ...(service.xaiSearch ? ["xai"] : []),
          ...(service.jinaKey ? ["jina"] : []),
          ...(service.searxngUrl ? ["searxng"] : []),
        ]);
        backend.enum = backend.enum.filter((name) => configured.has(name));
      }
    }
    return copy;
  });
}

export function internetToolNames() {
  return [...TOOLS.keys()];
}

export function internetPluginIds() {
  return PLUGINS.map((plugin) => plugin.id);
}

export async function executeInternetTool(service, name, args, options) {
  const tool = TOOLS.get(name);
  if (!tool)
    throw Object.assign(new Error(`Unknown ALTA internet tool: ${name}`), {
      status: 404,
      code: "alta_web_unknown_tool",
    });
  try {
    const signals = [options?.signal, service.lifecycleSignal].filter(Boolean);
    const value = await withDeadline(
      {
        ...options,
        signal: signals.length ? AbortSignal.any(signals) : undefined,
      },
      service.settings?.toolTimeoutMs ?? 90_000,
      (bounded) => tool.handler(service, args, bounded),
      { label: name, code: "alta_tool_deadline" },
    );
    service.recordTool?.(name, true);
    return value;
  } catch (error) {
    service.recordTool?.(name, false);
    throw error;
  }
}
