import assert from "node:assert/strict";
import test from "node:test";
import { getErrorMessage } from "../src/lib/error-message.ts";

test("API extraction errors retain the server detail for existing toast paths", () => {
  const error = {
    isAxiosError: true,
    message: "Request failed with status code 502",
    response: {
      status: 502,
      data: {
        detail: "Memory extraction failed. Check provider configuration.",
      },
    },
  };
  assert.equal(
    getErrorMessage(error),
    "Memory extraction failed. Check provider configuration.",
  );
});

test("Quick Test errors retain their message for the existing inline notification", () => {
  assert.equal(
    getErrorMessage(new Error("Test failed (502): Memory extraction failed.")),
    "Test failed (502): Memory extraction failed.",
  );
});
