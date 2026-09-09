import assert from "node:assert/strict";
import test from "node:test";
import { SnapshotFence } from "../src/lib/snapshot-fence.ts";

test("a delayed poll cannot overwrite a completed operator mutation", () => {
  const fence = new SnapshotFence();
  const slowRead = fence.begin();
  fence.invalidate();
  assert.equal(fence.accepts(slowRead), false);
  assert.equal(fence.accepts(fence.begin()), true);
});

test("newer explicit reads supersede old reads and their errors", () => {
  const fence = new SnapshotFence();
  const poll = fence.begin();
  const explicit = fence.begin();
  assert.equal(fence.accepts(poll), false);
  assert.equal(fence.accepts(explicit), true);
});
