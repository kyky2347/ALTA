export function invalid(message, code = "alta_finance_invalid_argument") {
  return Object.assign(new Error(message), { status: 400, code });
}

export function requiredText(value, name, pattern, maximum) {
  const text = String(value ?? "")
    .trim()
    .slice(0, maximum);
  if (!text || !pattern.test(text)) throw invalid(`Invalid or missing ${name}`);
  return text;
}

export function optionalText(value, name, pattern, maximum) {
  if (value === undefined || value === null || value === "") return "";
  return requiredText(value, name, pattern, maximum);
}

export function isoDate(value, fallback) {
  const text = String(value ?? fallback).trim();
  const parsed = new Date(`${text}T00:00:00Z`);
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(text) ||
    Number.isNaN(parsed.valueOf()) ||
    parsed.toISOString().slice(0, 10) !== text
  )
    throw invalid("Dates must use YYYY-MM-DD", "alta_finance_invalid_date");
  return text;
}

export function period(value, fallback = "") {
  const text = String(value ?? fallback).trim();
  if (!/^\d{4}(?:-\d{2}(?:-\d{2})?)?$/.test(text))
    throw invalid(
      "Periods must use YYYY, YYYY-MM, or YYYY-MM-DD",
      "alta_finance_invalid_period",
    );
  const [, month, day] = text.split("-").map(Number);
  if (
    (month !== undefined && (month < 1 || month > 12)) ||
    (day !== undefined && isoDate(text, "") !== text)
  )
    throw invalid(
      "Periods must contain a valid calendar date",
      "alta_finance_invalid_period",
    );
  return text;
}

export function dateBefore(days) {
  return new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);
}

export function dateToday() {
  return new Date().toISOString().slice(0, 10);
}

export function assertRange(from, to, label = "date") {
  if (from > to)
    throw invalid(
      `from_${label} must not exceed to_${label}`,
      `alta_finance_invalid_${label}_range`,
    );
}

export function assertPeriodRange(from, to) {
  const key = (value, upper) => {
    const [year, month, day] = value.split("-").map(Number);
    return (
      year * 10_000 +
      (month ?? (upper ? 12 : 1)) * 100 +
      (day ?? (upper ? 31 : 1))
    );
  };
  if (key(from, false) > key(to, true))
    throw invalid(
      "from_period must not exceed to_period",
      "alta_finance_invalid_period_range",
    );
}

export async function readJson(service, request, options) {
  const response = await service.readText(request, options);
  try {
    return JSON.parse(response.text);
  } catch {
    throw Object.assign(new Error("Financial source returned invalid JSON"), {
      status: 502,
      code: "alta_finance_invalid_response",
    });
  }
}

export async function readCsv(service, request, maximum, options) {
  const response = await service.readText(request, options);
  return parseCsv(response.text, maximum);
}

export function parseCsv(text, maximum) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (character === '"') quoted = false;
      else field += character;
    } else if (character === '"') quoted = true;
    else if (character === ",") {
      row.push(field);
      field = "";
    } else if (character === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
      if (rows.length > maximum) break;
    } else field += character;
  }
  if (field || row.length) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }
  const [headers = [], ...records] = rows;
  return records
    .slice(0, maximum)
    .map((values) =>
      Object.fromEntries(
        headers.map((header, index) => [header, values[index] || null]),
      ),
    );
}

export function provenance(publisher, sourceUrl) {
  return {
    publisher,
    source_url: sourceUrl,
    official: true,
    authentication: "none",
  };
}

export function boundedRecord(record, fields, maximumString = 500) {
  return Object.fromEntries(
    fields.flatMap((field) => {
      const value = record?.[field];
      return value === undefined
        ? []
        : [
            [
              field,
              typeof value === "string" ? value.slice(0, maximumString) : value,
            ],
          ];
    }),
  );
}

export function compactRecord(record) {
  return Object.fromEntries(
    Object.entries(record).filter(([, value]) => value !== undefined),
  );
}
