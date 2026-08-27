export function retryDelayMs(
  attempt,
  retryAfter,
  {
    baseMs = 500,
    maximumMs = 30_000,
    jitterMs = 350,
    now = Date.now,
    random = Math.random,
  } = {},
) {
  if (
    (typeof retryAfter === "string" && retryAfter.trim() !== "") ||
    (typeof retryAfter === "number" && Number.isFinite(retryAfter))
  ) {
    const seconds = Number(retryAfter);
    if (Number.isFinite(seconds) && seconds >= 0)
      return Math.min(seconds * 1000, maximumMs);
    if (typeof retryAfter === "string") {
      const date = Date.parse(retryAfter);
      if (Number.isFinite(date))
        return Math.min(Math.max(0, date - now()), maximumMs);
    }
  }
  const exponential = Math.min(
    baseMs * 2 ** Math.min(Math.max(0, attempt), 12),
    maximumMs,
  );
  return Math.min(
    maximumMs,
    exponential + Math.floor(random() * Math.max(0, jitterMs)),
  );
}
