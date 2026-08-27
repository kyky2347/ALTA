import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { deflateRawSync, gzipSync } from "node:zlib";
import { LocalFileReader } from "../local-files.mjs";

function zip(values) {
  const local = [];
  const central = [];
  let offset = 0;
  for (const value of values) {
    const name = Buffer.from(value.name);
    const content = Buffer.from(value.content);
    const compressed = deflateRawSync(content);
    const declaredSize = value.declaredSize ?? content.length;
    const localHeader = Buffer.alloc(30);
    localHeader.writeUInt32LE(0x04034b50, 0);
    localHeader.writeUInt16LE(20, 4);
    localHeader.writeUInt16LE(8, 8);
    localHeader.writeUInt32LE(compressed.length, 18);
    localHeader.writeUInt32LE(declaredSize, 22);
    localHeader.writeUInt16LE(name.length, 26);
    const centralHeader = Buffer.alloc(46);
    centralHeader.writeUInt32LE(0x02014b50, 0);
    centralHeader.writeUInt16LE(20, 4);
    centralHeader.writeUInt16LE(20, 6);
    centralHeader.writeUInt16LE(8, 10);
    centralHeader.writeUInt32LE(compressed.length, 20);
    centralHeader.writeUInt32LE(declaredSize, 24);
    centralHeader.writeUInt16LE(name.length, 28);
    centralHeader.writeUInt32LE(offset, 42);
    local.push(localHeader, name, compressed);
    central.push(centralHeader, name);
    offset += localHeader.length + name.length + compressed.length;
  }
  const directory = Buffer.concat(central);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(values.length, 8);
  end.writeUInt16LE(values.length, 10);
  end.writeUInt32LE(directory.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...local, directory, end]);
}

function workspace() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "alta-files-"));
}

test("local file pages are cacheable, lossless, and below the model item budget", async () => {
  const root = workspace();
  try {
    const expected = `标题\n${"dense 𒀀 data\n".repeat(180)}`;
    fs.writeFileSync(path.join(root, "notes.md"), expected);
    const reader = new LocalFileReader({ roots: [root] });
    const pages = [];
    let cursor = 0;
    do {
      const page = await reader.read({
        path: "notes.md",
        cursor,
        page_chars: 700,
      });
      assert(Buffer.byteLength(JSON.stringify(page)) <= 900);
      pages.push(page.content);
      cursor = page.next_cursor;
    } while (cursor !== null);
    assert.equal(pages.join(""), expected);
    assert.equal((await reader.read({ path: "notes.md" })).cached, true);
    assert.equal(reader.snapshot().entries, 1);
    reader.close();
    assert.equal(reader.snapshot().usedBytes, 0);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("workspace policy blocks sensitive paths before reading them", async () => {
  const root = workspace();
  const outsideRoot = workspace();
  const outside = path.join(outsideRoot, "outside.txt");
  try {
    fs.writeFileSync(outside, "outside");
    fs.writeFileSync(path.join(root, ".env"), "TOKEN=secret");
    fs.writeFileSync(path.join(root, ".env.example"), "TOKEN=");
    fs.writeFileSync(path.join(root, "private.pem"), "secret");
    fs.mkdirSync(path.join(root, "Resource API Keys"));
    fs.writeFileSync(
      path.join(root, "Resource API Keys", "fixture.rtf"),
      "unreadable fixture",
    );
    fs.mkdirSync(path.join(root, "SeCrEtS"));
    fs.writeFileSync(path.join(root, "SeCrEtS", "fixture.txt"), "blocked");
    fs.writeFileSync(path.join(root, "business.txt"), "ordinary text");
    fs.writeFileSync(path.join(root, "business.rtf"), "{\\rtf1 ordinary}");
    const reader = new LocalFileReader({ roots: [root] });
    for (const file of [
      outside,
      ".env",
      ".env.example",
      "private.pem",
      "Resource API Keys/fixture.rtf",
      "resource api keys/../Resource API Keys/fixture.rtf",
      "SeCrEtS/fixture.txt",
    ])
      await assert.rejects(() => reader.read({ path: file }), {
        code:
          file === outside
            ? "alta_file_outside_workspace"
            : "alta_file_sensitive_path",
      });
    fs.symlinkSync(
      path.join(root, "Resource API Keys"),
      path.join(root, "public-link"),
      process.platform === "win32" ? "junction" : "dir",
    );
    await assert.rejects(
      () => reader.read({ path: "public-link/fixture.rtf" }),
      { code: "alta_file_sensitive_path" },
    );
    assert.equal(
      (await reader.read({ path: "business.txt" })).content,
      "ordinary text",
    );
    assert.equal(
      (await reader.read({ path: "business.rtf" })).content,
      "ordinary",
    );
    fs.symlinkSync(
      outsideRoot,
      path.join(root, "escape"),
      process.platform === "win32" ? "junction" : "dir",
    );
    await assert.rejects(() => reader.read({ path: "escape/outside.txt" }), {
      code: "alta_file_outside_workspace",
    });
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
    fs.rmSync(outsideRoot, { recursive: true, force: true });
  }
});

test("portable parsers read Office, OpenDocument, EPUB, PDF, GZIP, and legacy files", async () => {
  const root = workspace();
  try {
    // prettier-ignore
    const fixtures = [
      ["sample.docx", zip([{ name: "word/document.xml", content: "<w:document><w:p><w:r><w:t>Hello document</w:t></w:r></w:p></w:document>" }]), "Hello document"],
      ["sample.xlsx", zip([{ name: "xl/sharedStrings.xml", content: "<sst><si><t>Revenue</t></si></sst>" }, { name: "xl/worksheets/sheet1.xml", content: '<worksheet><row><c r="A1" t="s"><v>0</v></c><c r="B1"><v>42</v></c></row></worksheet>' }]), "Revenue"],
      ["sample.pptx", zip([{ name: "ppt/slides/slide1.xml", content: "<p:sld><a:p><a:r><a:t>Quarterly result</a:t></a:r></a:p></p:sld>" }]), "Quarterly result"],
      ["sample.odt", zip([{ name: "content.xml", content: "<office:document><text:p>Open document</text:p></office:document>" }]), "Open document"],
      ["sample.epub", zip([{ name: "chapter.xhtml", content: "<html><body><h1>Chapter</h1><p>Book text</p></body></html>" }]), "Book text"],
      ["sample.pdf", Buffer.from("%PDF-1.4\n1 0 obj<</Length 40>>stream\nBT (Portable PDF text) Tj ET\nendstream\nendobj\n%%EOF", "latin1"), "Portable PDF text"],
      ["sample.txt.gz", gzipSync("compressed text"), "compressed text"],
      ["legacy.doc", Buffer.from("\0\0Readable legacy document text\0\0", "latin1"), "Readable legacy document text"],
    ];
    const reader = new LocalFileReader({ roots: [root] });
    for (const [name, content, expected] of fixtures) {
      fs.writeFileSync(path.join(root, name), content);
      const result = await reader.read({ path: name });
      assert.match(result.content, new RegExp(expected));
      assert(Buffer.byteLength(JSON.stringify(result)) <= 900);
    }
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("archive listing and entry reads are bounded against expansion bombs", async () => {
  const root = workspace();
  try {
    fs.writeFileSync(
      path.join(root, "bundle.zip"),
      zip([
        { name: "docs/readme.txt", content: "archive evidence" },
        { name: ".env", content: "TOKEN=archive-secret" },
        { name: ".ssh/id_rsa", content: "private" },
        { name: "private.pem", content: "private" },
        { name: "nested/Resource API Keys/value.txt", content: "private" },
      ]),
    );
    fs.writeFileSync(
      path.join(root, "bomb.zip"),
      zip([
        { name: "large.txt", content: "tiny", declaredSize: 32 * 1024 * 1024 },
      ]),
    );
    const reader = new LocalFileReader({ roots: [root] });
    const listing = await reader.read({ path: "bundle.zip" });
    assert.match(listing.content, /docs\/readme\.txt/);
    assert.doesNotMatch(
      listing.content,
      /\.env|\.ssh|private\.pem|Resource API Keys/,
    );
    const entry = await reader.read({
      path: "bundle.zip",
      section: "docs/readme.txt",
    });
    assert.match(entry.content, /archive evidence/);
    for (const section of [
      ".env",
      ".ssh/id_rsa",
      "private.pem",
      "nested/Resource API Keys/value.txt",
    ])
      await assert.rejects(() => reader.read({ path: "bundle.zip", section }), {
        code: "alta_file_sensitive_path",
      });
    await assert.rejects(
      () => reader.read({ path: "bomb.zip", section: "large.txt" }),
      { code: "alta_file_archive_limit" },
    );
    fs.writeFileSync(
      path.join(root, "ratio.gz"),
      gzipSync("x".repeat(2 * 1024 * 1024)),
    );
    const limited = new LocalFileReader({
      roots: [root],
      env: { ALTA_FILE_EXPANDED_MB: "1" },
    });
    await assert.rejects(() => limited.read({ path: "ratio.gz" }), {
      code: "alta_file_archive_limit",
    });
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
