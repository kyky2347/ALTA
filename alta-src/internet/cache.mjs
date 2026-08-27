export class BoundedCache {
  constructor(maxBytes, ttlMs, staleTtlMs = ttlMs) {
    this.maxBytes = maxBytes;
    this.ttlMs = ttlMs;
    this.staleTtlMs = staleTtlMs;
    this.bytes = 0;
    this.values = new Map();
  }

  get(key) {
    const entry = this.values.get(key);
    if (!entry) return null;
    if (entry.expiresAt <= Date.now()) {
      if (entry.staleUntil <= Date.now()) this.delete(key);
      return null;
    }
    return this.#touch(key, entry);
  }

  getStale(key) {
    const entry = this.values.get(key);
    if (!entry) return null;
    if (entry.staleUntil <= Date.now()) {
      this.delete(key);
      return null;
    }
    return this.#touch(key, entry);
  }

  set(key, value, ttlMs = this.ttlMs) {
    const serialized = JSON.stringify(value);
    const bytes = Buffer.byteLength(serialized);
    if (bytes > this.maxBytes) return;
    this.delete(key);
    this.values.set(key, {
      value: structuredClone(value),
      bytes,
      expiresAt: Date.now() + ttlMs,
      staleUntil: Date.now() + ttlMs + this.staleTtlMs,
    });
    this.bytes += bytes;
    while (this.bytes > this.maxBytes && this.values.size) {
      this.delete(this.values.keys().next().value);
    }
  }

  delete(key) {
    const entry = this.values.get(key);
    if (!entry) return;
    this.bytes -= entry.bytes;
    this.values.delete(key);
  }

  snapshot() {
    const now = Date.now();
    return {
      entries: this.values.size,
      staleEntries: [...this.values.values()].filter(
        (entry) => entry.expiresAt <= now && entry.staleUntil > now,
      ).length,
      usedBytes: this.bytes,
      limitBytes: this.maxBytes,
    };
  }

  clear() {
    this.values.clear();
    this.bytes = 0;
  }

  #touch(key, entry) {
    this.values.delete(key);
    this.values.set(key, entry);
    return structuredClone(entry.value);
  }
}
