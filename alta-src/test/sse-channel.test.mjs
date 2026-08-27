import test from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { setTimeout as delay } from "node:timers/promises";
import { HeartbeatHub, writeSseChunk } from "../sse-channel.mjs";

class FakeResponse extends EventEmitter {
  constructor({ backpressured = false } = {}) {
    super();
    this.destroyed = false;
    this.writableEnded = false;
    this.writableNeedDrain = backpressured;
    this.chunks = [];
  }

  write(chunk) {
    this.chunks.push(chunk);
    return !this.writableNeedDrain;
  }
}

test("SSE output waits for a slow client to drain", async () => {
  const response = new FakeResponse({ backpressured: true });
  let settled = false;
  const pending = writeSseChunk(response, "data: bounded\n\n").finally(() => {
    settled = true;
  });

  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(settled, false);
  assert.equal(response.listenerCount("drain"), 1);
  response.writableNeedDrain = false;
  response.emit("drain");
  await pending;

  assert.equal(settled, true);
  assert.equal(response.listenerCount("drain"), 0);
  assert.deepEqual(response.chunks, ["data: bounded\n\n"]);
});

test("one heartbeat timer serves every writable response", async () => {
  const hub = new HeartbeatHub(5);
  const writable = new FakeResponse();
  const backpressured = new FakeResponse({ backpressured: true });
  const unregisterWritable = hub.register(writable);
  const unregisterBackpressured = hub.register(backpressured);

  assert.deepEqual(hub.snapshot(), { listeners: 2, timerActive: true });
  await delay(30);
  assert.ok(writable.chunks.length > 0);
  assert.deepEqual(backpressured.chunks, []);

  unregisterWritable();
  unregisterBackpressured();
  assert.deepEqual(hub.snapshot(), { listeners: 0, timerActive: false });
});
