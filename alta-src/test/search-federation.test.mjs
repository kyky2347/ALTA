import test from "node:test";
import assert from "node:assert/strict";
import { executeSearch } from "../internet/search.mjs";

function contextFor({ brave = [], xai = [], searxng = [] }) {
  return {
    braveKey: "fixture-route",
    searxngUrl: "https://search.example/",
    xaiSearch: async () => ({ sources: xai }),
    request: async (url) => {
      const host = new URL(url).hostname;
      if (host === "api.search.brave.com")
        return { body: JSON.stringify({ grounding: { generic: brave } }) };
      if (host === "search.example")
        return { body: JSON.stringify({ results: searxng }) };
      throw Object.assign(new Error("public search unavailable"), {
        status: 503,
      });
    },
  };
}

function record(path, fields = {}) {
  return { url: `https://issuer.example/${path}`, title: path, ...fields };
}

const args = {
  query: "issuer evidence",
  maximum: 4,
  depth: "deep",
  allowed: [],
  excluded: [],
  freshness: "",
  language: "en",
  backend: "federated",
};

test("federated selection fairly interleaves successful engines within the result limit", async () => {
  const context = contextFor({
    brave: [record("a1"), record("a2"), record("a3"), record("a4")],
    xai: [record("b1"), record("b2")],
    searxng: [record("c1"), record("c2")],
  });
  const result = await executeSearch(context, args);
  assert.deepEqual(
    result.results.map((item) => item.title),
    ["a1", "b1", "c1", "a2"],
  );
  assert.deepEqual(result.backends, ["brave", "xai", "searxng"]);
  assert.deepEqual(await executeSearch(context, args), result);
});

test("duplicate URLs retain all engine provenance without consuming a fair-selection turn", async () => {
  const result = await executeSearch(
    contextFor({
      brave: [
        record("shared#first", { snippets: ["First excerpt"] }),
        record("shared#again", { snippets: ["Second excerpt"] }),
        record("a2"),
      ],
      xai: [record("shared#second"), record("b1")],
      searxng: [
        record("c1"),
        record("shared#third", { content: "Third excerpt" }),
      ],
    }),
    args,
  );
  assert.deepEqual(
    result.results.map((item) => item.url),
    ["shared", "b1", "c1", "a2"].map((path) => record(path).url),
  );
  assert.deepEqual(result.results[0].backends, ["brave", "xai", "searxng"]);
  assert.deepEqual(result.results[0].snippets, [
    "First excerpt",
    "Second excerpt",
    "Third excerpt",
  ]);
});

test("empty and exhausted engines do not prevent filling the bounded result set", async () => {
  const result = await executeSearch(
    contextFor({
      brave: [],
      xai: [record("shared")],
      searxng: [record("shared"), record("c2"), record("c3")],
    }),
    { ...args, maximum: 8 },
  );
  assert.deepEqual(
    result.results.map((item) => item.url),
    ["shared", "c2", "c3"].map((path) => record(path).url),
  );
  assert.deepEqual(result.results[0].backends, ["xai", "searxng"]);
});

test("fair selection preserves exact domain filtering and drops unsafe URL forms", async () => {
  const context = contextFor({
    brave: [
      { url: "not a url" },
      { url: "ftp://issuer.example/ftp" },
      { url: "https://credential@issuer.example/private" },
      { url: "https://unrelated.example/news" },
      record("a1"),
    ],
    xai: [
      record("b1"),
      { url: "https://issuer.example.attacker.example/news" },
    ],
    searxng: [record("c1")],
  });
  const scoped = await executeSearch(context, {
    ...args,
    maximum: 8,
    allowed: ["issuer.example"],
  });
  assert.deepEqual(
    scoped.results.map((item) => item.url),
    ["a1", "b1", "c1"].map((path) => record(path).url),
  );

  const excluded = await executeSearch(context, {
    ...args,
    maximum: 8,
    excluded: ["issuer.example"],
  });
  assert.deepEqual(
    excluded.results.map((item) => item.url),
    [
      "https://unrelated.example/news",
      "https://issuer.example.attacker.example/news",
    ],
  );
});
