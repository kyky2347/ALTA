function identityKey({ name, namespace }) {
  return JSON.stringify([namespace || null, name]);
}

function declaredFunctions(tools) {
  const identities = new Map();
  const add = (name, namespace) => {
    if (typeof name !== "string" || !name) return;
    const identity = { name, ...(namespace ? { namespace } : {}) };
    identities.set(identityKey(identity), identity);
  };
  for (const tool of tools ?? []) {
    if (tool?.type === "function") add(tool.name);
    else if (
      tool?.type === "namespace" &&
      typeof tool.name === "string" &&
      tool.name
    )
      for (const child of tool.tools ?? [])
        if (child?.type === "function") add(child.name, tool.name);
  }
  return identities;
}

function mcpQualifiedName(namespace, name) {
  if (!namespace.startsWith("mcp__")) return null;
  return `${namespace}${namespace.endsWith("__") ? "" : "__"}${name}`;
}

function bareName(identity) {
  if (identity.namespace) return identity.name;
  return identity.name.startsWith("mcp__")
    ? identity.name.slice(identity.name.lastIndexOf("__") + 2)
    : identity.name;
}

function splitQualifiedName(name) {
  const parts = name.split("::");
  return parts.length === 2 && parts.every(Boolean)
    ? { namespace: parts[0], name: parts[1] }
    : null;
}

/** Correct provider identity formatting only within the request's declared tools. */
export function restoreDeclaredToolCalls(value, tools, aliases = new Map()) {
  const declared = declaredFunctions(tools);
  const identities = [...declared.values()];
  const output = (value?.response ?? value)?.output;
  if (!Array.isArray(output)) return;
  for (const call of output) {
    if (
      call?.type !== "function_call" ||
      typeof call.name !== "string" ||
      (call.namespace != null && typeof call.namespace !== "string") ||
      declared.has(identityKey(call))
    )
      continue;
    const candidates = new Map();
    const qualified = !call.namespace ? splitQualifiedName(call.name) : null;
    const add = (identity) => {
      const key = identityKey(identity);
      if (declared.has(key)) candidates.set(key, declared.get(key));
    };
    // Some native providers add an underscore to gateway-generated aliases.
    // Match only a declared alias/target, never arbitrary name punctuation.
    for (const [alias, identity] of aliases)
      if (
        alias.replace(/_+/g, "_") === call.name.replace(/_+/g, "_") &&
        (!call.namespace || call.namespace === identity.namespace)
      )
        add(identity);
    for (const identity of identities) {
      if (call.namespace) {
        if (
          !identity.namespace &&
          identity.name === mcpQualifiedName(call.namespace, call.name)
        )
          add(identity);
      } else if (qualified) {
        if (
          (identity.namespace === qualified.namespace &&
            identity.name === qualified.name) ||
          (!identity.namespace &&
            identity.name ===
              mcpQualifiedName(qualified.namespace, qualified.name))
        )
          add(identity);
      } else if (
        bareName(identity) === call.name ||
        (identity.namespace &&
          mcpQualifiedName(identity.namespace, identity.name) === call.name)
      )
        add(identity);
    }
    // Ambiguity is not permission to choose a server. Leave it to the router
    // to reject unsupported calls instead of enabling an undeclared capability.
    if (candidates.size !== 1) continue;
    const identity = candidates.values().next().value;
    call.name = identity.name;
    if (identity.namespace) call.namespace = identity.namespace;
    else delete call.namespace;
  }
}
