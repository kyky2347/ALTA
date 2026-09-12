const TRANSIENT_STATUS = new Set([408, 409, 425, 429, 500, 502, 503, 504]);

function transient(error) {
  return !error?.status || TRANSIENT_STATUS.has(error.status);
}

/** Bounded circuit-breaker state for the fixed set of public-data backends. */
export class BackendHealth {
  #states = new Map();

  constructor({
    failureThreshold = 2,
    baseCooldownMs = 15_000,
    maxCooldownMs = 5 * 60_000,
    now = Date.now,
  } = {}) {
    this.failureThreshold = failureThreshold;
    this.baseCooldownMs = baseCooldownMs;
    this.maxCooldownMs = maxCooldownMs;
    this.now = now;
  }

  /** Return a request-owned lease, or null; settle with that same lease. */
  acquire(name, { force = false } = {}) {
    const state = this.#states.get(name);
    if (!state?.cooldownUntil)
      return Object.freeze({ name, generation: state?.generation ?? 0 });
    if (!force && state.cooldownUntil > this.now()) {
      state.suppressed += 1;
      return null;
    }
    if (state.probeInFlight) {
      state.suppressed += 1;
      return null;
    }
    state.probeInFlight = true;
    state.generation += 1;
    return Object.freeze({ name, generation: state.generation });
  }

  succeeded(name, lease) {
    if (!this.#owns(name, lease)) return;
    const state = this.#states.get(name);
    if (!state) return;
    if (state.probeInFlight) state.generation += 1;
    state.consecutiveFailures = 0;
    state.cooldownUntil = 0;
    state.probeInFlight = false;
    state.lastError = "";
  }

  failed(name, error, lease) {
    if (!this.#owns(name, lease)) return;
    const state = this.#state(name);
    if (state.probeInFlight) state.generation += 1;
    state.probeInFlight = false;
    if (!transient(error)) return;
    state.consecutiveFailures += 1;
    state.lastError = String(error?.message ?? error).slice(0, 300);
    if (state.consecutiveFailures < this.failureThreshold) return;
    state.opens += 1;
    state.generation += 1;
    state.consecutiveFailures = 0;
    state.cooldownUntil =
      this.now() +
      Math.min(
        this.baseCooldownMs * 2 ** Math.min(state.opens - 1, 8),
        this.maxCooldownMs,
      );
  }

  cancelled(name, lease) {
    if (!this.#owns(name, lease)) return;
    const state = this.#states.get(name);
    if (!state?.probeInFlight) return;
    // Cancellation is not a provider failure. Release only this request's
    // recovery probe; late completions from an older generation cannot reset
    // or release a probe that another request has since acquired.
    state.probeInFlight = false;
    state.generation += 1;
  }

  snapshot() {
    const now = this.now();
    return Object.fromEntries(
      [...this.#states]
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([name, state]) => [
          name,
          {
            state:
              state.cooldownUntil > now
                ? "open"
                : state.probeInFlight
                  ? "half-open"
                  : "closed",
            retryInMs: Math.max(0, state.cooldownUntil - now),
            opens: state.opens,
            suppressed: state.suppressed,
            lastError: state.lastError,
          },
        ]),
    );
  }

  #state(name) {
    let state = this.#states.get(name);
    if (!state) {
      state = {
        consecutiveFailures: 0,
        cooldownUntil: 0,
        probeInFlight: false,
        opens: 0,
        suppressed: 0,
        lastError: "",
        generation: 0,
      };
      this.#states.set(name, state);
    }
    return state;
  }

  #owns(name, lease) {
    return (
      !lease ||
      (lease.name === name &&
        lease.generation === (this.#states.get(name)?.generation ?? 0))
    );
  }
}
