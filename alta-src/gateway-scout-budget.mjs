const MAX_ATTEMPTS = 3;
const MAX_TRACKED_RUNS = 1_000;
const RETENTION_MS = 24 * 60 * 60 * 1_000;

function reject(message, status, code) {
  throw Object.assign(new Error(message), { status, code });
}

// The operator supplies headers in thread configuration, not in model arguments.
// A deadline-bound attempt ID stays unchanged across transport retries.
export function admitBoundedScoutToolCall(req, context, message) {
  if (message?.method !== "tools/call") return null;
  const runId = req.headers["x-alta-run-id"];
  const rawLimit = req.headers["x-alta-max-tool-calls"];
  const attemptId = req.headers["x-alta-attempt-id"];
  if (runId === undefined && rawLimit === undefined && attemptId === undefined)
    return null;
  if (
    typeof runId !== "string" ||
    !/^run_[a-f0-9]{32}$/.test(runId) ||
    typeof rawLimit !== "string" ||
    !/^([0-9]|1[0-2])$/.test(rawLimit) ||
    (attemptId !== undefined &&
      (typeof attemptId !== "string" || !/^[a-f0-9]{64}$/.test(attemptId)))
  )
    reject(
      "Invalid ALTA Scout tool budget headers",
      400,
      "alta_scout_budget_invalid",
    );

  const limit = Number(rawLimit);
  const key = attemptId ?? "legacy";
  const now = performance.now();
  context.scoutToolCalls ??= new Map();
  let run = context.scoutToolCalls.get(runId);
  if (!run) {
    for (const [id, value] of context.scoutToolCalls) {
      if (now - value.createdAt >= RETENTION_MS)
        context.scoutToolCalls.delete(id);
    }
    // Never evict a recent budget merely to admit a new run.
    if (context.scoutToolCalls.size >= MAX_TRACKED_RUNS)
      reject(
        "ALTA Scout budget registry is full",
        429,
        "alta_scout_budget_capacity",
      );
    run = { limit, createdAt: now, attempts: new Map() };
    context.scoutToolCalls.set(runId, run);
  }
  if (run.limit !== limit)
    reject(
      "ALTA Scout budget cannot change within a run",
      400,
      "alta_scout_budget_invalid",
    );
  if (!run.attempts.has(key) && run.attempts.size >= MAX_ATTEMPTS)
    reject(
      "ALTA Scout retry budget exhausted",
      429,
      "alta_scout_retry_budget_exhausted",
    );
  const previous = run.attempts.get(key) ?? 0;
  if (previous >= limit)
    reject(
      "ALTA Scout tool call budget exhausted",
      429,
      "alta_scout_tool_budget_exhausted",
    );
  run.attempts.set(key, previous + 1);
  return { limit, used: previous + 1, remaining: limit - previous - 1 };
}
