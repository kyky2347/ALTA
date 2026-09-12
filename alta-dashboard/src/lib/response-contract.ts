type RecordValue = Record<string, unknown>;

export function isRecord(value: unknown): value is RecordValue {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function strings(value: RecordValue, fields: string[]) {
  return fields.every((field) => typeof value[field] === "string");
}

function rows(value: unknown, fields: string[] = []) {
  return (
    Array.isArray(value) &&
    value.every((row) => isRecord(row) && strings(row, fields))
  );
}

/** Validate the structures the UI dereferences before replacing a good snapshot.
 * Additional backend fields remain forward compatible; malformed records do not.
 */
export function validConsolePayload(path: string, value: unknown): boolean {
  if (!isRecord(value)) return false;
  const route = path.split("?", 1)[0];
  if (
    ["/control/execution-mode", "/control/broker-credentials/tiger"].includes(
      route,
    )
  )
    return (
      validConsolePayload("/control/capital", value) &&
      isRecord(value.execution) &&
      ["shadow", "broker_paper"].includes(String(value.execution.requested)) &&
      ["shadow", "broker_paper", "blocked", "close_only"].includes(
        String(value.execution.effective),
      ) &&
      typeof value.execution.revision === "string" &&
      /^[a-f0-9]{64}$/.test(value.execution.revision)
    );
  if (route === "/control/agent-models") {
    const settings = value.settings;
    const model = (route: unknown) =>
      isRecord(route) && strings(route, ["provider", "model"]);
    return (
      typeof value.revision === "string" &&
      /^[a-f0-9]{64}$/.test(value.revision) &&
      Array.isArray(value.scoutIds) &&
      value.scoutIds.every((id) => typeof id === "string") &&
      Array.isArray(value.providers) &&
      value.providers.every((id) => typeof id === "string") &&
      isRecord(settings) &&
      isRecord(settings.roles) &&
      isRecord(settings.scouts) &&
      [
        "scout",
        "thesis",
        "disconfirming",
        "moderator",
        "expression",
        "audit",
        "position",
      ].every((id) => model((settings.roles as RecordValue)[id])) &&
      Object.values(settings.scouts).every(model)
    );
  }
  if (route === "/control/bootstrap" || route === "/control/state") {
    return (
      isRecord(value.console) &&
      typeof value.console.instanceId === "string" &&
      typeof value.console.protocolVersion === "number" &&
      isRecord(value.runtime) &&
      typeof value.runtime.ready === "boolean" &&
      isRecord(value.safety) &&
      value.safety.brokerEnvironment === "PAPER" &&
      (value.operation === null || isRecord(value.operation)) &&
      (route !== "/control/bootstrap" || typeof value.csrfToken === "string")
    );
  }
  if (route === "/proxy/api/v1/mvp/status") {
    const fields: Record<string, string[]> = {
      sources: ["id"],
      pipeline: ["id", "eventType"],
      runs: ["id", "role", "status"],
      agents: ["id", "status"],
      candidates: ["id", "title"],
      opportunities: ["id", "title", "status"],
      ranks: ["id", "opportunityId", "book", "rankingRunId"],
      expressions: ["id", "opportunityId", "kind", "status"],
      shadowPositions: ["id", "expressionId", "symbol", "status"],
      assessments: ["id", "opportunityId", "assessor", "verdict"],
      discussions: ["id", "opportunityId", "eventType"],
    };
    return (
      strings(value, ["status", "environment"]) &&
      Number.isSafeInteger(value.eventCursor) &&
      Number(value.eventCursor) >= 0 &&
      Object.entries(fields).every(([key, required]) =>
        rows(value[key], required),
      )
    );
  }
  if (route === "/proxy/api/v1/system/runtime")
    return isRecord(value.config) && rows(value.minds);
  if (route === "/proxy/api/v1/events")
    return (
      rows(value.events, ["eventId", "eventType", "knownAt"]) &&
      (value.events as RecordValue[]).every(
        (event) =>
          Number.isSafeInteger(event.cursor) &&
          Number(event.cursor) > 0 &&
          isRecord(event.payload),
      )
    );
  if (route.startsWith("/control/credentials"))
    return (
      strings(value, ["revision"]) &&
      Array.isArray(value.configuredSlots) &&
      rows(value.slots, ["slot", "label", "category"]) &&
      (value.slots as RecordValue[]).every((slot) =>
        isRecord(slot.verification),
      ) &&
      rows(value.providerNetwork, ["category"]) &&
      (value.providerNetwork as RecordValue[]).every((group) =>
        Array.isArray(group.providers),
      ) &&
      isRecord(value.verification) &&
      isRecord(value.trading)
    );
  if (route.startsWith("/control/capital"))
    return (
      value.environment === "PAPER" &&
      typeof value.enabled === "boolean" &&
      typeof value.requestedEnabled === "boolean" &&
      isRecord(value.riskPolicy) &&
      rows(value.audit, ["id", "action", "result"]) &&
      (value.snapshot === null ||
        (isRecord(value.snapshot) &&
          value.snapshot.paper === true &&
          value.snapshot.accountBinding === true &&
          isRecord(value.snapshot.assets) &&
          rows(value.snapshot.positions, ["symbol"]) &&
          rows(value.snapshot.orders, ["symbol", "status"])))
    );
  return true;
}
