export async function withDeadline(
  options,
  deadlineMs,
  operation,
  { label = "source", code = "alta_source_deadline" } = {},
) {
  const parent = options?.signal;
  parent?.throwIfAborted();
  const controller = new AbortController();
  let rejectPending;
  const cancelled = new Promise((_, reject) => {
    rejectPending = reject;
  });
  const stop = (error) => {
    if (controller.signal.aborted) return;
    controller.abort(error);
    rejectPending(error);
  };
  const cancel = () => stop(parent.reason ?? new Error(`${label} cancelled`));
  parent?.addEventListener("abort", cancel, { once: true });
  const timer =
    deadlineMs > 0
      ? setTimeout(
          () =>
            stop(
              Object.assign(
                new Error(`${label} exceeded its ${deadlineMs} ms deadline`),
                { status: 504, code },
              ),
            ),
          deadlineMs,
        )
      : null;
  try {
    // A late result/rejection remains handled, but cannot revive cancelled work.
    // Invoke synchronously, but capture synchronous throws as well. An adapter
    // can cancel its parent and throw in the same stack; both rejections need
    // race handlers or cancellation would become an unhandled rejection.
    const work = new Promise((resolve) =>
      resolve(operation({ ...options, signal: controller.signal })),
    );
    return await Promise.race([work, cancelled]);
  } finally {
    if (timer) clearTimeout(timer);
    parent?.removeEventListener("abort", cancel);
  }
}
