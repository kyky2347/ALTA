import { errorMessage } from "./support.mjs";

const PACING = new WeakMap();

function claimPacedSlot(service, name, intervalMs) {
  if (!intervalMs) return;
  let sources = PACING.get(service);
  if (!sources) {
    sources = new Map();
    PACING.set(service, sources);
  }
  const now = Date.now();
  const availableAt = sources.get(name) ?? 0;
  if (availableAt > now)
    throw Object.assign(
      new Error(`${name} is locally paced for ${availableAt - now} ms`),
      { status: 429, code: "alta_source_paced" },
    );
  sources.set(name, now + intervalMs);
}

export async function runSource(
  service,
  namespace,
  source,
  options,
  operation,
  { intervalMs = 0, deadlineMs = 0 } = {},
) {
  const name = `${namespace}:${source}`;
  claimPacedSlot(service, name, intervalMs);
  if (service.backendHealth && !service.backendHealth.acquire(name))
    throw Object.assign(new Error(`${source} is cooling down after failures`), {
      status: 503,
      code: "alta_source_circuit_open",
    });
  try {
    const value = await withDeadline(options, deadlineMs, operation);
    service.backendHealth?.succeeded(name);
    return value;
  } catch (error) {
    if (!options?.signal?.aborted) service.backendHealth?.failed(name, error);
    throw error;
  }
}

export async function settleSources(
  service,
  namespace,
  sources,
  options,
  operation,
  { intervals = {}, deadlines = {} } = {},
) {
  const settled = await Promise.allSettled(
    sources.map((source) =>
      runSource(
        service,
        namespace,
        source,
        options,
        (sourceOptions) => operation(source, sourceOptions),
        {
          intervalMs: intervals[source] ?? 0,
          deadlineMs: deadlines[source] ?? 0,
        },
      ),
    ),
  );
  const values = [];
  const failures = [];
  settled.forEach((item, index) => {
    const source = sources[index];
    if (item.status === "fulfilled") values.push({ source, value: item.value });
    else failures.push({ source, error: errorMessage(item.reason) });
  });
  return { values, failures };
}

async function withDeadline(options, deadlineMs, operation) {
  if (!deadlineMs) return operation(options);
  const controller = new AbortController();
  const parent = options?.signal;
  const cancel = () =>
    controller.abort(parent.reason ?? new Error("source request cancelled"));
  if (parent?.aborted) cancel();
  else parent?.addEventListener("abort", cancel, { once: true });
  let rejectTimeout;
  const timeout = new Promise((_, reject) => {
    rejectTimeout = reject;
  });
  const timer = setTimeout(() => {
    const error = Object.assign(
      new Error(`source exceeded its ${deadlineMs} ms deadline`),
      { status: 504, code: "alta_source_deadline" },
    );
    controller.abort(error);
    rejectTimeout(error);
  }, deadlineMs);
  timer.unref?.();
  try {
    return await Promise.race([
      operation({ ...options, signal: controller.signal }),
      timeout,
    ]);
  } finally {
    clearTimeout(timer);
    parent?.removeEventListener("abort", cancel);
  }
}
