import { errorMessage } from "./support.mjs";
import { SourcePacer } from "../source-pacer.mjs";
import { withDeadline } from "../deadline.mjs";

const PACING = new WeakMap();

function sourcePacer(service, name) {
  let sources = PACING.get(service);
  if (!sources) {
    sources = new Map();
    PACING.set(service, sources);
  }
  let pacer = sources.get(name);
  if (!pacer) {
    pacer = new SourcePacer();
    sources.set(name, pacer);
  }
  return pacer;
}

export async function runSource(
  service,
  namespace,
  source,
  options,
  operation,
  { intervalMs = 0, deadlineMs = 0 } = {},
) {
  const lifecycleSignal = service.lifecycleSignal;
  const signal = lifecycleSignal
    ? options?.signal
      ? AbortSignal.any([options.signal, lifecycleSignal])
      : lifecycleSignal
    : options?.signal;
  const sourceOptions = signal ? { ...options, signal } : options;
  signal?.throwIfAborted();
  const name = `${namespace}:${source}`;
  const admit = () => {
    signal?.throwIfAborted();
    const lease = service.backendHealth?.acquire(name);
    if (service.backendHealth && !lease)
      throw Object.assign(
        new Error(`${source} is cooling down after failures`),
        {
          status: 503,
          code: "alta_source_circuit_open",
        },
      );
    return lease;
  };
  const execute = async (lease) => {
    try {
      const value = await withDeadline(sourceOptions, deadlineMs, operation);
      signal?.throwIfAborted();
      service.backendHealth?.succeeded(name, lease);
      return value;
    } catch (error) {
      if (signal?.aborted) service.backendHealth?.cancelled(name, lease);
      else service.backendHealth?.failed(name, error, lease);
      throw error;
    }
  };
  return intervalMs
    ? sourcePacer(service, name).schedule({
        name,
        intervalMs,
        signal,
        admit,
        execute,
      })
    : execute(admit());
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
