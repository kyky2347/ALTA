import { createHash } from "node:crypto";

/** One source of truth: a mode is an execution authority, not a UI preference. */
export function executionMode(capital) {
  const requested = capital.requestedEnabled ? "broker_paper" : "shadow";
  const effective = capital.requestedEnabled
    ? capital.enabled
      ? capital.closeOnly
        ? "close_only"
        : "broker_paper"
      : "blocked"
    : capital.authorizationError
      ? "blocked"
      : "shadow";
  const revision = createHash("sha256")
    .update(
      JSON.stringify([
        capital.authorizationGeneration,
        capital.configurationFingerprint,
        capital.requestedEnabled,
        capital.enabled,
        capital.closeOnly,
        capital.posture,
      ]),
    )
    .digest("hex");
  return {
    requested,
    effective,
    revision,
    provider: "tiger",
    environment: "PAPER",
  };
}

export function validateModeRequest(body, capital) {
  if (
    !body ||
    typeof body !== "object" ||
    Array.isArray(body) ||
    Object.keys(body).sort().join() !== "confirmation,mode,revision" ||
    !["shadow", "broker_paper"].includes(body.mode) ||
    body.confirmation !==
      (body.mode === "shadow" ? "USE SHADOW" : "ENABLE TIGER PAPER")
  )
    throw Object.assign(new Error("execution_mode_invalid"), {
      code: "execution_mode_invalid",
      statusCode: 400,
    });
  if (body.revision !== executionMode(capital).revision)
    throw Object.assign(new Error("execution_mode_conflict"), {
      code: "execution_mode_conflict",
      statusCode: 409,
    });
  return body.mode;
}
