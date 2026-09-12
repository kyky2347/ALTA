/** Select a reproducible excerpt without rewriting or summarizing source text. */
export function textWindow(text, { limit, offset = 0, focus = "" }) {
  const startOffset = Number(offset);
  if (
    !Number.isSafeInteger(startOffset) ||
    startOffset < 0 ||
    startOffset > 4_000_000
  )
    throw Object.assign(
      new Error("offset must be an integer from 0 to 4000000"),
      {
        status: 400,
        code: "alta_web_invalid_offset",
      },
    );
  if (typeof focus !== "string" || focus.length > 200)
    throw Object.assign(new Error("focus must be at most 200 characters"), {
      status: 400,
      code: "alta_web_invalid_focus",
    });
  const match = focus.trim()
    ? text.toLowerCase().indexOf(focus.trim().toLowerCase(), startOffset)
    : -1;
  const start = Math.min(
    text.length,
    match >= 0 ? Math.max(startOffset, match - 240) : startOffset,
  );
  const end = Math.min(text.length, start + limit);
  return {
    text: text.slice(start, end),
    truncated: start > 0 || end < text.length,
    ...(focus || startOffset
      ? {
          text_start: start,
          text_end: end,
          total_chars: text.length,
          focus_matched: focus.trim() ? match >= 0 : null,
        }
      : {}),
  };
}
