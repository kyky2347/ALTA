export const READ_ONLY = {
  readOnlyHint: true,
  destructiveHint: false,
  idempotentHint: true,
  openWorldHint: true,
};

export function defineTool(name, title, description, inputSchema, handler) {
  return {
    definition: {
      name,
      title,
      description,
      inputSchema,
      annotations: READ_ONLY,
    },
    handler,
  };
}

export function boundedInteger(value, fallback, minimum, maximum) {
  const parsed = Number(value ?? fallback);
  return Number.isFinite(parsed)
    ? Math.trunc(Math.min(Math.max(parsed, minimum), maximum))
    : fallback;
}

export function uniqueStrings(values, maximum, maxLength = 2_000) {
  if (!Array.isArray(values)) return [];
  return [
    ...new Set(
      values
        .map((value) => String(value).trim().slice(0, maxLength))
        .filter(Boolean),
    ),
  ].slice(0, maximum);
}

export function errorMessage(reason) {
  return String(reason?.message ?? reason).slice(0, 1_000);
}
