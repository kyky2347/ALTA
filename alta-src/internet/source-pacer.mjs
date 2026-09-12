import { performance } from "node:perf_hooks";

export const SOURCE_QUEUE_LIMIT = 8;
export const SOURCE_QUEUE_WAIT_MS = 15_000;

function pacedError(message) {
  return Object.assign(new Error(message), {
    status: 429,
    code: "alta_source_paced",
  });
}

/** FIFO dispatch pacing; HTTP concurrency remains owned by InternetService. */
export class SourcePacer {
  #queue = [];
  #nextAt = 0;
  #timer;
  #draining = false;

  constructor({
    maxQueue = SOURCE_QUEUE_LIMIT,
    maxWaitMs = SOURCE_QUEUE_WAIT_MS,
  } = {}) {
    if (
      !Number.isInteger(maxQueue) ||
      maxQueue < 1 ||
      maxQueue > SOURCE_QUEUE_LIMIT ||
      !Number.isFinite(maxWaitMs) ||
      maxWaitMs <= 0 ||
      maxWaitMs > SOURCE_QUEUE_WAIT_MS
    )
      throw new RangeError("source pacing limits exceed their hard bounds");
    this.maxQueue = maxQueue;
    this.maxWaitMs = maxWaitMs;
  }

  schedule({ name, intervalMs, signal, admit, execute }) {
    signal?.throwIfAborted();
    if (!Number.isFinite(intervalMs) || intervalMs < 0)
      throw new RangeError("source pacing interval must be non-negative");
    if (this.#queue.length >= this.maxQueue)
      return Promise.reject(pacedError(`${name} local source queue is full`));
    return new Promise((resolve, reject) => {
      const entry = {
        name,
        intervalMs,
        signal,
        admit,
        execute,
        resolve,
        reject,
        expiresAt: performance.now() + this.maxWaitMs,
      };
      entry.cancel = () => {
        const index = this.#queue.indexOf(entry);
        if (index < 0) return;
        this.#queue.splice(index, 1);
        signal.removeEventListener("abort", entry.cancel);
        reject(signal.reason);
        this.#drain();
      };
      this.#queue.push(entry);
      signal?.addEventListener("abort", entry.cancel, { once: true });
      this.#drain();
    });
  }

  #drain() {
    if (this.#draining) return;
    this.#draining = true;
    clearTimeout(this.#timer);
    this.#timer = undefined;
    try {
      while (this.#queue.length) {
        const entry = this.#queue[0];
        const now = performance.now();
        if (now < entry.expiresAt && now < this.#nextAt) {
          this.#timer = setTimeout(
            () => this.#drain(),
            Math.ceil(Math.min(entry.expiresAt, this.#nextAt) - now),
          );
          return;
        }
        this.#queue.shift();
        entry.signal?.removeEventListener("abort", entry.cancel);
        try {
          entry.signal?.throwIfAborted();
          if (now >= entry.expiresAt)
            throw pacedError(
              `${entry.name} exceeded its ${this.maxWaitMs} ms local queue wait`,
            );
          // Admission is synchronous and just-in-time: a queued request never
          // owns a stale circuit lease, and rejected work consumes no slot.
          const admission = entry.admit();
          this.#nextAt = performance.now() + entry.intervalMs;
          entry.resolve(entry.execute(admission));
        } catch (error) {
          entry.reject(error);
        }
      }
    } finally {
      this.#draining = false;
    }
  }
}
