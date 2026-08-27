function disconnectedError() {
  return Object.assign(new Error("ALTA response client disconnected"), {
    code: "alta_client_disconnected",
  });
}

function waitForDrain(response, signal) {
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      response.removeListener("drain", onDrain);
      response.removeListener("close", onClose);
      signal?.removeEventListener("abort", onAbort);
    };
    const onDrain = () => {
      cleanup();
      resolve();
    };
    const onClose = () => {
      cleanup();
      reject(disconnectedError());
    };
    const onAbort = () => {
      cleanup();
      reject(signal.reason ?? new Error("ALTA response cancelled"));
    };
    response.once("drain", onDrain);
    response.once("close", onClose);
    signal?.addEventListener("abort", onAbort, { once: true });
    if (response.destroyed || response.writableEnded) onClose();
    else if (signal?.aborted) onAbort();
  });
}

export async function writeSseChunk(response, chunk, signal) {
  if (response.destroyed || response.writableEnded) throw disconnectedError();
  if (!response.write(chunk)) await waitForDrain(response, signal);
}

export function writeSseComment(response, comment) {
  if (
    response.destroyed ||
    response.writableEnded ||
    response.writableNeedDrain
  )
    return false;
  return response.write(`: ${comment}\n\n`);
}

export class HeartbeatHub {
  #responses = new Set();
  #timer = null;

  constructor(intervalMs) {
    this.intervalMs = intervalMs;
  }

  register(response) {
    this.#responses.add(response);
    this.#start();
    let registered = true;
    return () => {
      if (!registered) return;
      registered = false;
      this.#responses.delete(response);
      if (!this.#responses.size) this.#stop();
    };
  }

  comment(response, value) {
    return writeSseComment(response, value);
  }

  snapshot() {
    return {
      listeners: this.#responses.size,
      timerActive: this.#timer !== null,
    };
  }

  close() {
    this.#responses.clear();
    this.#stop();
  }

  #start() {
    if (this.#timer) return;
    this.#timer = setInterval(() => {
      for (const response of this.#responses) {
        if (response.destroyed || response.writableEnded) {
          this.#responses.delete(response);
          continue;
        }
        writeSseComment(response, "keep-alive");
      }
      if (!this.#responses.size) this.#stop();
    }, this.intervalMs);
    this.#timer.unref?.();
  }

  #stop() {
    if (this.#timer) clearInterval(this.#timer);
    this.#timer = null;
  }
}
