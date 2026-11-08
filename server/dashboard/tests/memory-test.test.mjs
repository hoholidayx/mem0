import assert from "node:assert/strict";
import test from "node:test";
import { assertMemoryTestResult } from "../src/utils/memory-test.ts";

test("Quick Test requires an actual added or updated memory", () => {
  for (const event of ["ADD", "UPDATE"]) {
    assert.doesNotThrow(() =>
      assertMemoryTestResult({ results: [{ id: "test-memory", event }] }),
    );
  }
});

test("empty or unchanged extraction cannot be shown as memory created", () => {
  for (const results of [
    [],
    [{ id: "old", event: "NONE" }],
    [{ event: "ADD" }],
    [{ id: "", event: "ADD" }],
  ]) {
    assert.throws(
      () => assertMemoryTestResult({ results }),
      /No memory was created/,
    );
  }
});

test("invalid responses cannot be shown as success", () => {
  for (const data of [
    null,
    {},
    { results: null },
    { detail: "Extraction failed" },
  ]) {
    assert.throws(() => assertMemoryTestResult(data), /unexpected response/);
  }
});
