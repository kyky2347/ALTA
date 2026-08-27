export class InflightCoalescer {
  #closed = false;
  #entries = new Map();
  #joined = 0;
  #overflow = 0;
  #started = 0;

  constructor(limit = 256) {
    this.limit = limit;
  }

  run(key, operation, signal) {
    if (signal?.aborted)
      return Promise.reject(signal.reason ?? new Error("request cancelled"));
    if (this.#closed)
      return Promise.reject(
        Object.assign(new Error("ALTA internet service is draining"), {
          status: 503,
          code: "alta_draining",
        }),
      );

    let entry = this.#entries.get(key);
    if (!entry) {
      if (this.#entries.size >= this.limit) {
        this.#overflow += 1;
        return operation(signal);
      }
      const controller = new AbortController();
      entry = {
        controller,
        settled: false,
        subscribers: 0,
        promise: null,
      };
      entry.promise = Promise.resolve()
        .then(() => operation(controller.signal))
        .finally(() => {
          entry.settled = true;
          if (this.#entries.get(key) === entry) this.#entries.delete(key);
        });
      this.#entries.set(key, entry);
      this.#started += 1;
    } else {
      this.#joined += 1;
    }

    entry.subscribers += 1;
    return new Promise((resolve, reject) => {
      let finished = false;
      const finish = () => {
        if (finished) return false;
        finished = true;
        signal?.removeEventListener("abort", onAbort);
        entry.subscribers -= 1;
        if (!entry.settled && entry.subscribers === 0)
          entry.controller.abort(
            new Error("all request subscribers cancelled"),
          );
        return true;
      };
      const onAbort = () => {
        if (finish()) reject(signal.reason ?? new Error("request cancelled"));
      };
      signal?.addEventListener("abort", onAbort, { once: true });
      entry.promise.then(
        (value) => {
          if (finish()) resolve(value);
        },
        (error) => {
          if (finish()) reject(error);
        },
      );
    });
  }

  snapshot() {
    return {
      active: this.#entries.size,
      limit: this.limit,
      started: this.#started,
      joined: this.#joined,
      overflow: this.#overflow,
      closed: this.#closed,
    };
  }

  close() {
    this.#closed = true;
  }
}
