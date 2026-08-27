import test from "node:test";
import assert from "node:assert/strict";
import { stripRemoteAccessEnvironment } from "../remote-access-policy.mjs";

test("research child environments strip repository credentials", () => {
  const environment = stripRemoteAccessEnvironment({
    PATH: "/fixture/bin",
    ALTA_GATEWAY_TOKEN: "fixture-local-token",
    GITHUB_TOKEN: "fixture-remote-token",
    GH_TOKEN: "fixture-remote-token",
    GIT_SSH_COMMAND: "ssh fixture",
    SSH_AUTH_SOCK: "/fixture/ssh-agent",
  });

  assert.deepEqual(environment, {
    PATH: "/fixture/bin",
    ALTA_GATEWAY_TOKEN: "fixture-local-token",
  });
});

test("repository credential stripping preserves non-secret process metadata", () => {
  const environment = stripRemoteAccessEnvironment({
    GITHUB_ACTIONS: "true",
    GH_ENTERPRISE_TOKEN: "fixture-remote-token",
    GIT_AUTHOR_NAME: "Fixture Author",
    LANG: "en_US.UTF-8",
  });

  assert.deepEqual(environment, {
    GIT_AUTHOR_NAME: "Fixture Author",
    LANG: "en_US.UTF-8",
  });
});
