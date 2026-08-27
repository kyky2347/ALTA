import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { unlinkFiles, walkFiles } from "../file-inventory.mjs";

test("file inventory and deletion stay bounded across a large tree", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "alta-inventory-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const files = Array.from({ length: 160 }, (_, index) =>
    path.join(root, `group-${index % 8}`, `file-${index}.bin`),
  );
  for (const file of files) {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, "alta");
  }

  const entries = await walkFiles(root, 4);
  assert.deepEqual(
    entries
      .map(({ file, size }) => ({ file, size }))
      .sort((a, b) => a.file.localeCompare(b.file)),
    files
      .map((file) => ({ file, size: 4 }))
      .sort((a, b) => a.file.localeCompare(b.file)),
  );

  const missing = path.join(root, "already-gone.bin");
  const deletion = await unlinkFiles([...files, missing], 4);
  assert.deepEqual(deletion.failures, []);
  assert.deepEqual(new Set(deletion.removed), new Set([...files, missing]));
  assert.equal((await walkFiles(root, 4)).length, 0);
});
