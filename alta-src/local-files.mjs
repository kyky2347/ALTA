import fs from "node:fs";
import path from "node:path";
import { gunzipSync, inflateRawSync, inflateSync } from "node:zlib";
import { BoundedCache } from "./internet/cache.mjs";
import { InflightCoalescer } from "./internet/inflight.mjs";
import { CapacityLimiter } from "./resource-control.mjs";

const MIB = 1024 * 1024;
const RESULT_BYTES = 900;
// prettier-ignore
const PDF_WARNING = "No standard PDF text found; scanned/encrypted PDFs require an OCR-capable agent.";
// prettier-ignore
const BINARY_WARNING = "Heuristic printable-text extraction was used for this legacy or unknown format.";
// prettier-ignore
const MEDIA_NOTICE = "Binary media file. Hand this workspace path to an image/audio/video-capable agent; no base64 entered context.";
// prettier-ignore
const TEXT = new Set(".c .conf .cpp .css .csv .eml .go .h .htm .html .ini .java .js .json .jsonl .log .md .mjs .py .rs .rtf .sh .sql .svg .toml .ts .tsv .txt .xml .yaml .yml".split(" "));
// prettier-ignore
const MEDIA = new Set(".aac .avi .flac .gif .jpeg .jpg .m4a .mkv .mov .mp3 .mp4 .ogg .png .wav .webm .webp".split(" "));
// prettier-ignore
const ZIP_FORMATS = new Set(".docm .docx .dotx .epub .odp .ods .odt .potx .pptm .pptx .xlsm .xlsx .xltx .zip".split(" "));
// prettier-ignore
const BLOCKED = new Set(
  ".aws .config .git .alta .ssh auth.json credential credentials credentials.json llm-api-keys resource-api-keys secret secrets secrets.json"
    .split(" "),
);
const BLOCKED_NAMES = new Set(["llm api keys", "resource api keys"]);

function fail(message, code, status = 400) {
  throw Object.assign(new Error(message), {
    code: `alta_file_${code}`,
    status,
  });
}

function integer(value, fallback, minimum, maximum) {
  const parsed = Number(value ?? fallback);
  return Number.isFinite(parsed)
    ? Math.trunc(Math.min(Math.max(parsed, minimum), maximum))
    : fallback;
}

function decode(buffer) {
  if (buffer[0] === 0xff && buffer[1] === 0xfe)
    return buffer.subarray(2).toString("utf16le");
  if (buffer[0] === 0xfe && buffer[1] === 0xff) {
    const swapped = Buffer.from(buffer.subarray(2));
    swapped.swap16();
    return swapped.toString("utf16le");
  }
  return buffer
    .toString("utf8")
    .replace(/^\uFEFF/, "")
    .replace(/\r\n?/g, "\n")
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "");
}

function entities(value) {
  // prettier-ignore
  const named = { amp: "&", apos: "'", gt: ">", lt: "<", nbsp: " ", quot: '"' };
  return value
    .replace(/&#(?:(x)([\da-f]+)|(\d+));/gi, (_, hex, digits, decimal) =>
      String.fromCodePoint(
        Math.min(Number.parseInt(digits ?? decimal, hex ? 16 : 10), 0x10ffff),
      ),
    )
    .replace(
      /&(amp|apos|gt|lt|nbsp|quot);/gi,
      (_, name) => named[name.toLowerCase()],
    );
}

function xmlText(value) {
  return entities(
    value
      .replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi, " ")
      .replace(/<(?:w:tab|w:br|br)\b[^>]*\/?\s*>/gi, "\n")
      .replace(/<\/(?:w:p|a:p|text:p|p|h[1-6]|tr)>/gi, "\n")
      .replace(/<\/(?:w:tc|table:table-cell|td|th)>/gi, "\t")
      .replace(/<text:s\b[^>]*\/>/gi, " ")
      .replace(/<[^>]+>/g, " "),
  )
    .replace(/[ \t]+\n/g, "\n")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function plainText(buffer, extension, section = "") {
  let text = decode(buffer);
  if (extension === ".rtf")
    text = text
      .replace(/\\'[\da-f]{2}/gi, (item) =>
        Buffer.from(item.slice(2), "hex").toString("latin1"),
      )
      .replace(/\\(?:par|line)\b/g, "\n")
      .replace(/\\tab\b/g, "\t")
      .replace(/\\[a-z]+-?\d* ?|[{}]/gi, "")
      .replace(/\\([{}\\])/g, "$1");
  else if ([".htm", ".html", ".svg", ".xml"].includes(extension))
    text = xmlText(text);
  return {
    format: extension.slice(1) || "text",
    text,
    sections: section ? [section] : [],
  };
}

function printable(buffer) {
  const ascii = buffer.toString("latin1").match(/[\x20-\x7e]{5,}/g) ?? [];
  const wide = buffer.toString("utf16le").match(/[\u0020-\uD7FF]{5,}/g) ?? [];
  return [...wide, ...ascii].join("\n").slice(0, 2 * MIB);
}

function sensitivePath(value) {
  const parts = String(value).replaceAll("\\", "/").toLowerCase().split("/");
  // prettier-ignore
  return parts.some((name) => name.startsWith(".") || BLOCKED.has(name) || BLOCKED_NAMES.has(name)) || /\.(?:key|p12|pem|pfx)$/i.test(value);
}

function expand(operation) {
  try {
    return operation();
  } catch (error) {
    if (error?.code === "ERR_BUFFER_TOO_LARGE")
      fail("Expanded data limit exceeded", "archive_limit", 413);
    throw error;
  }
}

function zipDirectory(buffer, maximum) {
  let end = -1;
  for (
    let offset = buffer.length - 22;
    offset >= Math.max(0, buffer.length - 65_557);
    offset -= 1
  ) {
    if (buffer.readUInt32LE(offset) === 0x06054b50) {
      end = offset;
      break;
    }
  }
  if (end < 0) fail("Invalid or unsupported ZIP archive", "invalid_archive");
  const count = buffer.readUInt16LE(end + 10);
  let offset = buffer.readUInt32LE(end + 16);
  if (count === 0xffff || offset === 0xffffffff || count > maximum)
    fail("ZIP entry limit exceeded", "archive_limit", 413);
  const entries = [];
  for (let index = 0; index < count; index += 1) {
    if (
      offset + 46 > buffer.length ||
      buffer.readUInt32LE(offset) !== 0x02014b50
    )
      fail("Invalid ZIP directory", "invalid_archive");
    const nameBytes = buffer.readUInt16LE(offset + 28);
    const extraBytes = buffer.readUInt16LE(offset + 30);
    const commentBytes = buffer.readUInt16LE(offset + 32);
    entries.push({
      name: buffer
        .subarray(offset + 46, offset + 46 + nameBytes)
        .toString("utf8")
        .replaceAll("\\", "/")
        .replace(/^\/+/, "")
        .slice(0, 500),
      flags: buffer.readUInt16LE(offset + 8),
      method: buffer.readUInt16LE(offset + 10),
      compressed: buffer.readUInt32LE(offset + 20),
      size: buffer.readUInt32LE(offset + 24),
      offset: buffer.readUInt32LE(offset + 42),
    });
    offset += 46 + nameBytes + extraBytes + commentBytes;
  }
  return entries;
}

function unzip(buffer, entry, maximum) {
  if (entry.flags & 1) fail("Encrypted ZIP entry", "encrypted");
  if (entry.size > maximum)
    fail("Expanded file limit exceeded", "archive_limit", 413);
  // prettier-ignore
  if (entry.offset + 30 > buffer.length || buffer.readUInt32LE(entry.offset) !== 0x04034b50)
    fail("Invalid ZIP entry", "invalid_archive");
  const start =
    entry.offset +
    30 +
    buffer.readUInt16LE(entry.offset + 26) +
    buffer.readUInt16LE(entry.offset + 28);
  const source = buffer.subarray(start, start + entry.compressed);
  if (source.length !== entry.compressed)
    fail("Truncated ZIP entry", "invalid_archive");
  let value;
  if (entry.method === 0) value = Buffer.from(source);
  else if (entry.method === 8)
    value = expand(() => inflateRawSync(source, { maxOutputLength: maximum }));
  else fail(`Unsupported ZIP method ${entry.method}`, "archive_method");
  if (value.length !== entry.size)
    fail("ZIP entry size mismatch", "invalid_archive");
  return value;
}

function sequence(name) {
  return Number(name.match(/(\d+)(?=\.[^.]+$)/)?.[1] ?? 0);
}

function zipDocument(buffer, extension, section, limits) {
  // prettier-ignore
  const entries = zipDirectory(buffer, limits.entries).filter(({ name }) => !sensitivePath(name));
  // prettier-ignore
  const names = entries.map(({ name }) => name).filter((name) => !name.endsWith("/"));
  if (extension === ".zip") {
    if (!section)
      return {
        format: "zip",
        text: entries
          .map(
            ({ name, size, method }) =>
              `${name}\t${size} bytes\tmethod ${method}`,
          )
          .join("\n"),
        sections: names,
      };
    const entry = entries.find(({ name }) => name === section);
    if (!entry) fail("ZIP section was not found", "section_not_found", 404);
    return plainText(
      unzip(buffer, entry, limits.expanded),
      path.extname(entry.name),
      entry.name,
    );
  }
  let parts;
  if ([".xlsm", ".xlsx", ".xltx"].includes(extension))
    parts = entries
      .filter(({ name }) =>
        /^(?:xl\/sharedStrings|xl\/worksheets\/sheet\d+)\.xml$/.test(name),
      )
      .sort((left, right) => sequence(left.name) - sequence(right.name));
  else if ([".docm", ".docx", ".dotx"].includes(extension))
    // prettier-ignore
    parts = entries.filter(({ name }) => /^word\/(?:document|footnotes|endnotes|header\d+|footer\d+)\.xml$/.test(name));
  else if ([".potx", ".pptm", ".pptx"].includes(extension))
    parts = entries
      .filter(({ name }) => /^ppt\/slides\/slide\d+\.xml$/.test(name))
      .sort((left, right) => sequence(left.name) - sequence(right.name));
  else if ([".odp", ".ods", ".odt"].includes(extension))
    parts = entries.filter(({ name }) => name === "content.xml");
  else
    parts = entries
      .filter(({ name }) => /\.(?:xhtml?|html)$/i.test(name))
      .slice(0, 64);
  if (!parts.length)
    fail("Document has no readable content parts", "document_structure");
  let expanded = 0;
  const text = parts.map((entry) => {
    expanded += entry.size;
    if (expanded > limits.expanded)
      fail("Expanded document limit exceeded", "archive_limit", 413);
    return `${entry.name}\n${xmlText(
      decode(unzip(buffer, entry, limits.expanded - expanded + entry.size)),
    )}`;
  });
  return {
    format: extension.slice(1),
    text: text.join("\n\n"),
    sections: parts.map(({ name }) => name),
  };
}

function pdfDocument(buffer, maximum) {
  const source = buffer.toString("latin1");
  const streams = [source];
  let expanded = 0;
  for (const match of source.matchAll(
    /<<(.*?)>>\s*stream\r?\n([\s\S]*?)\r?\nendstream/g,
  )) {
    if (streams.length >= 64 || expanded >= maximum) break;
    try {
      const remaining = maximum - expanded;
      const value = /FlateDecode/.test(match[1])
        ? inflateSync(Buffer.from(match[2], "latin1"), {
            maxOutputLength: remaining,
          }).toString("latin1")
        : match[2].slice(0, remaining);
      expanded += Buffer.byteLength(value, "latin1");
      streams.push(value);
    } catch {}
  }
  const text = streams
    .flatMap((stream) =>
      [...stream.matchAll(/\(((?:\\.|[^\\()])*)\)/g)].map((match) =>
        match[1].replace(/\\[nrt]/g, " ").replace(/\\([()\\])/g, "$1"),
      ),
    )
    .join(" ")
    .replace(/\s{2,}/g, " ")
    .trim();
  return {
    format: "pdf",
    text: text || printable(buffer),
    warnings: text ? [] : [PDF_WARNING],
  };
}

function parse(buffer, filename, section, limits, depth = 0) {
  const extension = path.extname(filename).toLowerCase();
  if (depth > 2) fail("Nested archive limit exceeded", "archive_limit", 413);
  const zipMagic = buffer.subarray(0, 4).equals(Buffer.from("PK\u0003\u0004"));
  if (ZIP_FORMATS.has(extension) || zipMagic)
    return zipDocument(
      buffer,
      ZIP_FORMATS.has(extension) ? extension : ".zip",
      section,
      limits,
    );
  if (extension === ".gz")
    return parse(
      expand(() => gunzipSync(buffer, { maxOutputLength: limits.expanded })),
      filename.slice(0, -3),
      section,
      limits,
      depth + 1,
    );
  if (extension === ".pdf" || buffer.toString("ascii", 0, 5) === "%PDF-")
    return pdfDocument(buffer, limits.expanded);
  if (TEXT.has(extension)) return plainText(buffer, extension);
  if (MEDIA.has(extension))
    return {
      format: extension.slice(1),
      text: MEDIA_NOTICE,
    };
  return {
    format: extension.slice(1) || "binary",
    text: printable(buffer),
    warnings: [BINARY_WARNING],
  };
}

function compact(base, text, cursor, requested) {
  const metadata = { ...base, content: "" };
  for (const field of ["sections", "warnings"])
    if (Buffer.byteLength(JSON.stringify(metadata)) > RESULT_BYTES - 64)
      delete metadata[field];
  const build = (length) => {
    let end = cursor + length;
    if (end < text.length && /[\uD800-\uDBFF]/.test(text[end - 1])) end -= 1;
    return {
      ...metadata,
      next_cursor: end < text.length ? end : null,
      truncated: end < text.length,
      content: text.slice(cursor, end),
    };
  };
  let low = 0;
  let high = Math.min(requested, text.length - cursor);
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (Buffer.byteLength(JSON.stringify(build(middle))) <= RESULT_BYTES)
      low = middle;
    else high = middle - 1;
  }
  return build(low);
}

function clipped(values, count, length) {
  return values?.length
    ? values.slice(0, count).map((value) => value.slice(0, length))
    : undefined;
}

export class LocalFileReader {
  constructor({ roots = [], env = process.env } = {}) {
    this.closed = false;
    this.roots = roots.map((root) => fs.realpathSync(root));
    this.limits = {
      file: integer(env.ALTA_FILE_MAX_MB, 16, 1, 64) * MIB,
      expanded: integer(env.ALTA_FILE_EXPANDED_MB, 8, 1, 32) * MIB,
      entries: integer(env.ALTA_FILE_ARCHIVE_ENTRIES, 128, 1, 512),
    };
    this.cache = new BoundedCache(
      integer(env.ALTA_FILE_CACHE_MB, 16, 4, 128) * MIB,
      integer(env.ALTA_FILE_CACHE_TTL_MINUTES, 5, 1, 60) * 60_000,
    );
    this.inflight = new InflightCoalescer(64);
    this.limiter = new CapacityLimiter({
      limit: integer(env.ALTA_FILE_CONCURRENCY, 2, 1, 8),
      queueLimit: integer(env.ALTA_FILE_QUEUE_LIMIT, 64, 0, 512),
      queueTimeoutMs: 30_000,
      name: "ALTA file parsing capacity",
    });
  }

  async read(
    {
      path: requestedPath,
      section = "",
      cursor = 0,
      page_chars: pageChars = 600,
    } = {},
    { signal } = {},
  ) {
    const requestedSection = String(section ?? "");
    if (requestedSection.length > 500)
      fail("A valid bounded archive section is required", "invalid_path");
    if (requestedSection && sensitivePath(requestedSection))
      fail("Sensitive or internal path is blocked", "sensitive_path", 403);
    const resolved = await this.#resolve(requestedPath);
    const stat = await fs.promises.stat(resolved.file);
    if (!stat.isFile()) fail("ALTA reads regular files only", "not_regular");
    if (stat.size > this.limits.file)
      fail("File exceeds the ALTA size limit", "too_large", 413);
    const selected = requestedSection;
    const key = `${resolved.file}\0${stat.size}\0${stat.mtimeMs}\0${selected}`;
    let document = this.cache.get(key);
    const cached = Boolean(document);
    if (!document)
      document = await this.inflight.run(
        key,
        async (sharedSignal) => {
          const current = this.cache.get(key);
          if (current) return current;
          const release = await this.limiter.acquire(sharedSignal);
          try {
            const buffer = await fs.promises.readFile(resolved.file, {
              signal: sharedSignal,
            });
            if (buffer.length > this.limits.file)
              fail("File changed beyond the ALTA size limit", "too_large", 413);
            const parsed = parse(buffer, resolved.file, selected, this.limits);
            parsed.text = String(parsed.text ?? "").slice(
              0,
              this.limits.expanded,
            );
            if (!this.closed) this.cache.set(key, parsed);
            return parsed;
          } finally {
            release();
          }
        },
        signal,
      );
    const start = integer(cursor, 0, 0, document.text.length);
    return compact(
      {
        path: resolved.display.replace(/[^\x20-\x7e]/g, "?").slice(0, 160),
        format: String(document.format)
          .replace(/[^\w+-]/g, "")
          .slice(0, 40),
        size_bytes: stat.size,
        cursor: start,
        total_chars: document.text.length,
        cached,
        sections: clipped(document.sections, 8, 80),
        warnings: clipped(document.warnings, 2, 160),
      },
      document.text,
      start,
      integer(pageChars, 600, 128, 700),
    );
  }

  snapshot() {
    return {
      ...this.cache.snapshot(),
      capacity: this.limiter.snapshot(),
      inflight: this.inflight.snapshot(),
    };
  }

  close() {
    this.closed = true;
    this.cache.clear();
    this.limiter.close();
    this.inflight.close();
  }

  async #resolve(value) {
    const requested = String(value ?? "");
    if (!requested || requested.length > 4_096 || requested.includes("\0"))
      fail("A valid bounded file path is required", "invalid_path");
    if (!this.roots.length)
      fail("Local file reading is not configured", "disabled", 503);
    const candidate = path.isAbsolute(requested)
      ? path.resolve(requested)
      : path.resolve(this.roots[0], requested);
    const requestedRoot = this.roots.find((item) => {
      const relative = path.relative(item, candidate);
      return (
        relative === "" ||
        (!relative.startsWith(`..${path.sep}`) &&
          relative !== ".." &&
          !path.isAbsolute(relative))
      );
    });
    if (requestedRoot && sensitivePath(path.relative(requestedRoot, candidate)))
      fail("Sensitive or internal path is blocked", "sensitive_path", 403);
    const file = await fs.promises
      .realpath(candidate)
      .catch(() => fail("File was not found", "not_found", 404));
    const root = this.roots.find((item) => {
      const relative = path.relative(item, file);
      return (
        relative === "" ||
        (!relative.startsWith(`..${path.sep}`) &&
          relative !== ".." &&
          !path.isAbsolute(relative))
      );
    });
    if (!root)
      fail("File is outside the allowed workspace", "outside_workspace", 403);
    const relative = path.relative(root, file);
    if (sensitivePath(relative))
      fail("Sensitive or internal path is blocked", "sensitive_path", 403);
    return { file, display: relative || path.basename(file) };
  }
}
