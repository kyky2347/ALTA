import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import test from "node:test";
import { runBrokerProcess } from "../broker-connections.mjs";

function launch(result, observed) {
  return (_command, args, options) => {
    observed.args = args;
    observed.options = options;
    const child = new EventEmitter();
    child.stdout = new PassThrough();
    child.stdin = new PassThrough();
    child.kill = () => {};
    child.stdin.on("data", (body) => {
      observed.body = JSON.parse(body);
    });
    setImmediate(() => {
      child.stdout.write(JSON.stringify(result));
      child.emit("close", 0);
    });
    return child;
  };
}

test("broker subprocess has a narrow environment, stdin credentials and allowlisted actions", async () => {
  const observed = {};
  const result = await runBrokerProcess(
    "python",
    "/project",
    { OPENAI_API_KEY: "do-not-pass", GH_TOKEN: "do-not-pass" },
    { action: "save", profile: {} },
    launch({ data: { saved: true } }, observed),
  );
  assert.equal(result.saved, true);
  assert.deepEqual(observed.args, ["-m", "alta_brokers"]);
  assert.deepEqual(Object.keys(observed.options.env).sort(), [
    "ALTA_CREDENTIALS_DIR",
    "HOME",
    "PATH",
    "PYTHONUNBUFFERED",
  ]);
  assert.equal(observed.body.action, "save");
  for (const action of ["submit", "authorize", "cancel", "live"])
    assert.throws(
      () => runBrokerProcess("python", "/project", {}, { action }),
      { code: "broker_action_unavailable" },
    );
});

test("broker error text cannot escape as a provider credential or raw account response", async () => {
  await assert.rejects(
    runBrokerProcess(
      "python",
      "/project",
      {},
      { action: "catalog" },
      launch({ error: { code: "provider-error secret=value" } }, {}),
    ),
    { code: "broker_operation_failed" },
  );
  await assert.rejects(
    runBrokerProcess(
      "python",
      "/project",
      {},
      { action: "catalog" },
      launch({ error: { code: "broker_profile_conflict" } }, {}),
    ),
    { statusCode: 409 },
  );
});
