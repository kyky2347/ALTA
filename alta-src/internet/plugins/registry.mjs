import { academicPlugin } from "./academic.mjs";
import { corePlugin } from "./core.mjs";
import { discoveryPlugin } from "./discovery.mjs";
import { financePlugin } from "./finance.mjs";
import { filesPlugin } from "./files.mjs";
import { newsPlugin } from "./news.mjs";
import { researchPlugin } from "./research.mjs";
import { socialPlugin } from "./social.mjs";
import { tradingViewPlugin } from "./tradingview.mjs";

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

export function internetToolDefinitions() {
  return [...TOOLS.values()].map(({ definition }) =>
    structuredClone(definition),
  );
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
    const value = await tool.handler(service, args, options);
    service.recordTool?.(name, true);
    return value;
  } catch (error) {
    service.recordTool?.(name, false);
    throw error;
  }
}
