import process from "node:process";

export function boundedNumber(value, fallback, minimum, maximum) {
  const parsed = Number(value ?? fallback);
  return Number.isFinite(parsed)
    ? Math.min(Math.max(parsed, minimum), maximum)
    : fallback;
}

export function numberSetting(name, fallback, minimum, maximum) {
  return boundedNumber(process.env[name], fallback, minimum, maximum);
}

export function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    const cleanup = () => signal?.removeEventListener("abort", cancel);
    const timer = setTimeout(() => {
      cleanup();
      resolve();
    }, ms);
    const cancel = () => {
      clearTimeout(timer);
      cleanup();
      reject(signal.reason ?? new Error("operation cancelled"));
    };
    if (signal?.aborted) return cancel();
    signal?.addEventListener("abort", cancel, { once: true });
  });
}

export class CapacityError extends Error {
  constructor(message, code = "alta_capacity_exceeded") {
    super(message);
    this.name = "CapacityError";
    this.code = code;
    this.status = 503;
    this.retryable = false;
  }
}

export async function acquireCapacityLease(limiters, signal) {
  const releases = [];
  try {
    for (const limiter of limiters) {
      if (limiter) releases.push(await limiter.acquire(signal));
    }
  } catch (error) {
    for (const release of releases.reverse()) release();
    throw error;
  }
  let released = false;
  return () => {
    if (released) return;
    released = true;
    for (const release of releases.reverse()) release();
  };
}

export class CapacityLimiter {
  #active = 0;
  #closed = false;
  #queue = [];

  constructor({ limit, queueLimit, queueTimeoutMs, name }) {
    this.limit = limit;
    this.queueLimit = queueLimit;
    this.queueTimeoutMs = queueTimeoutMs;
    this.name = name;
  }

  acquire(signal) {
    if (signal?.aborted)
      return Promise.reject(signal.reason ?? new Error("request cancelled"));
    if (this.#closed)
      return Promise.reject(
        new CapacityError(`${this.name} is draining`, "alta_draining"),
      );
    if (this.#active < this.limit) return Promise.resolve(this.#grant());
    if (this.#queue.length >= this.queueLimit)
      return Promise.reject(
        new CapacityError(`${this.name} queue is full`, "alta_queue_full"),
      );

    return new Promise((resolve, reject) => {
      const entry = { resolve, reject, signal, timer: null, onAbort: null };
      const remove = () => {
        const index = this.#queue.indexOf(entry);
        if (index >= 0) this.#queue.splice(index, 1);
      };
      entry.timer = setTimeout(() => {
        remove();
        this.#cleanupEntry(entry);
        reject(
          new CapacityError(
            `${this.name} queue wait timed out`,
            "alta_queue_timeout",
          ),
        );
      }, this.queueTimeoutMs);
      entry.onAbort = () => {
        remove();
        this.#cleanupEntry(entry);
        reject(signal.reason ?? new Error("request cancelled"));
      };
      if (signal?.aborted) return entry.onAbort();
      signal?.addEventListener("abort", entry.onAbort, { once: true });
      this.#queue.push(entry);
    });
  }

  close() {
    this.#closed = true;
    for (const entry of this.#queue.splice(0)) {
      this.#cleanupEntry(entry);
      entry.reject(
        new CapacityError(`${this.name} is draining`, "alta_draining"),
      );
    }
  }

  setLimit(limit) {
    this.limit = Math.max(1, Math.floor(limit));
    this.#drainQueue();
  }

  snapshot() {
    return {
      name: this.name,
      limit: this.limit,
      active: this.#active,
      queued: this.#queue.length,
      queueLimit: this.queueLimit,
      closed: this.#closed,
    };
  }

  #cleanupEntry(entry) {
    clearTimeout(entry.timer);
    entry.signal?.removeEventListener("abort", entry.onAbort);
  }

  #grant() {
    this.#active += 1;
    let released = false;
    return () => {
      if (released) return;
      released = true;
      this.#active -= 1;
      this.#drainQueue();
    };
  }

  #drainQueue() {
    while (!this.#closed && this.#active < this.limit && this.#queue.length) {
      const entry = this.#queue.shift();
      if (entry.signal?.aborted) {
        this.#cleanupEntry(entry);
        entry.reject(entry.signal.reason ?? new Error("request cancelled"));
        continue;
      }
      this.#cleanupEntry(entry);
      entry.resolve(this.#grant());
    }
  }
}

export class ByteBudget {
  #used = 0;

  constructor(limit) {
    this.limit = limit;
  }

  reserve(bytes) {
    if (this.#used + bytes > this.limit)
      throw new CapacityError(
        "ALTA request memory budget is exhausted",
        "alta_memory_budget",
      );
    this.#used += bytes;
  }

  release(bytes) {
    this.#used = Math.max(0, this.#used - bytes);
  }

  snapshot() {
    return { usedBytes: this.#used, limitBytes: this.limit };
  }
}

export class RetryCoordinator {
  #providers = new Map();

  constructor({ now = Date.now } = {}) {
    this.now = now;
  }

  async wait(provider, signal, maximumDelayMs = Number.POSITIVE_INFINITY) {
    const state = this.#state(provider);
    const delay = Math.max(0, state.blockedUntil - this.now());
    if (delay > maximumDelayMs)
      throw Object.assign(
        new Error("ALTA provider retry budget is exhausted"),
        {
          code: "alta_retry_budget_exhausted",
          retryable: false,
        },
      );
    if (delay > 0) {
      const jitter = Math.min(2_000, Math.max(250, state.failures * 250));
      await sleep(
        Math.min(maximumDelayMs, delay + Math.floor(Math.random() * jitter)),
        signal,
      );
    }
  }

  defer(provider, requestedDelayMs) {
    const state = this.#state(provider);
    const now = this.now();
    if (state.blockedUntil <= now) state.failures += 1;
    const exponential = Math.min(
      500 * 2 ** Math.min(state.failures, 8),
      120_000,
    );
    const requested = Math.max(0, Number(requestedDelayMs) || 0);
    const delay = Math.max(requested, exponential);
    state.blockedUntil = Math.max(state.blockedUntil, now + delay);
  }

  success(provider) {
    const state = this.#state(provider);
    state.failures = 0;
    state.blockedUntil = 0;
  }

  snapshot() {
    return Object.fromEntries(
      [...this.#providers].map(([name, state]) => [
        name,
        {
          consecutiveFailures: state.failures,
          retryInMs: Math.max(0, state.blockedUntil - this.now()),
        },
      ]),
    );
  }

  #state(provider) {
    if (!this.#providers.has(provider))
      this.#providers.set(provider, { failures: 0, blockedUntil: 0 });
    return this.#providers.get(provider);
  }
}

export class ProviderConcurrencyController {
  #providers = new Map();

  constructor(
    limiters,
    { recoverySuccesses = 8, reductionCooldownMs = 5_000, now = Date.now } = {},
  ) {
    this.recoverySuccesses = recoverySuccesses;
    this.reductionCooldownMs = reductionCooldownMs;
    this.now = now;
    for (const [provider, limiter] of limiters) {
      this.#providers.set(provider, {
        limiter,
        configuredLimit: limiter.limit,
        currentLimit: limiter.limit,
        successes: 0,
        reductions: 0,
        lastReductionAt: Number.NEGATIVE_INFINITY,
      });
    }
  }

  overload(provider) {
    const state = this.#providers.get(provider);
    if (!state) return;
    state.successes = 0;
    const now = this.now();
    if (now - state.lastReductionAt < this.reductionCooldownMs) return;
    const next = Math.max(1, Math.ceil(state.currentLimit / 2));
    if (next === state.currentLimit) return;
    state.lastReductionAt = now;
    state.currentLimit = next;
    state.reductions += 1;
    state.limiter.setLimit(next);
  }

  success(provider) {
    const state = this.#providers.get(provider);
    if (!state || state.currentLimit >= state.configuredLimit) return;
    state.successes += 1;
    if (state.successes < this.recoverySuccesses * state.currentLimit) return;
    state.successes = 0;
    state.currentLimit += 1;
    state.limiter.setLimit(state.currentLimit);
  }

  snapshot() {
    return Object.fromEntries(
      [...this.#providers].map(([provider, state]) => [
        provider,
        {
          configuredLimit: state.configuredLimit,
          currentLimit: state.currentLimit,
          recoveryProgress: state.successes,
          reductions: state.reductions,
        },
      ]),
    );
  }
}

export class LatencyMetrics {
  #providers = new Map();

  observe(provider, { queueMs, upstreamMs, totalMs, succeeded }) {
    const state = this.#providers.get(provider) ?? {
      samples: 0,
      failures: 0,
      queueMs: 0,
      upstreamMs: 0,
      totalMs: 0,
    };
    const weight = state.samples === 0 ? 1 : 0.125;
    state.samples += 1;
    if (!succeeded) state.failures += 1;
    state.queueMs = this.#update(state.queueMs, queueMs, weight);
    state.upstreamMs = this.#update(state.upstreamMs, upstreamMs, weight);
    state.totalMs = this.#update(state.totalMs, totalMs, weight);
    this.#providers.set(provider, state);
  }

  snapshot() {
    return Object.fromEntries(
      [...this.#providers].map(([provider, state]) => [
        provider,
        {
          samples: state.samples,
          failures: state.failures,
          queueMsEwma: Math.round(state.queueMs),
          upstreamMsEwma: Math.round(state.upstreamMs),
          totalMsEwma: Math.round(state.totalMs),
        },
      ]),
    );
  }

  #update(previous, value, weight) {
    const sample = Math.max(0, Number(value) || 0);
    return previous + weight * (sample - previous);
  }
}
