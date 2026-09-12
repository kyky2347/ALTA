import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { resolveLocale, LOCALES } from "../src/lib/locale.ts";

test("locale selection preserves choice and recognises Hong Kong and Cantonese preferences", () => {
  assert.equal(LOCALES.length, 3);
  assert.deepEqual(
    LOCALES.map((item) => item.label),
    ["English", "简体中文", "繁體中文"],
  );
  for (const browser of [
    "zh-HK",
    "zh-MO",
    "zh-TW",
    "zh-Hant",
    "zh-Hant-HK",
    "yue",
    "yue-Hant-HK",
  ])
    assert.equal(resolveLocale(null, [browser]), "zh-HK");
  assert.equal(resolveLocale("en", ["zh-HK"]), "en");
  assert.equal(resolveLocale("zh-HK", ["en"]), "zh-HK");
  assert.equal(resolveLocale("invalid", ["zh-CN"]), "zh-CN");
  assert.equal(resolveLocale(null, ["fr", "en-US"]), "en");
});
test("all three catalogs have identical keys and interpolation contracts", () => {
  const catalogs = ["en", "zh-CN", "zh-HK"].map((locale) =>
    JSON.parse(
      fs.readFileSync(
        new URL(`../src/lib/locales/${locale}.json`, import.meta.url),
        "utf8",
      ),
    ),
  );
  const [english] = catalogs;
  for (const catalog of catalogs) {
    assert.deepEqual(Object.keys(catalog).sort(), Object.keys(english).sort());
    for (const [key, text] of Object.entries(catalog)) {
      assert.equal(typeof text, "string");
      assert(text.trim(), key);
      assert.equal(
        /(?<!\{)\{[a-zA-Z_]\w*\}(?!\})/.test(text),
        false,
        `unexpanded single-brace placeholder: ${key}`,
      );
      assert.deepEqual(
        [...text.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort(),
        [...english[key].matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort(),
        key,
      );
    }
  }
});
