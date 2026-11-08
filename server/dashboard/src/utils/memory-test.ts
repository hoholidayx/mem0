/** A successful HTTP response alone does not prove that extraction created a memory. */
export function assertMemoryTestResult(data: unknown): void {
  const results =
    data && typeof data === "object" && "results" in data
      ? data.results
      : undefined;
  if (!Array.isArray(results)) {
    throw new Error(
      "The memory test returned an unexpected response. Please check the server logs and try again.",
    );
  }
  if (
    !results.some(
      (result) =>
        result &&
        (result.event === "ADD" || result.event === "UPDATE") &&
        typeof result.id === "string" &&
        result.id.length > 0,
    )
  ) {
    throw new Error(
      "No memory was created or updated. Try a new factual message, or check the extraction instructions and provider configuration.",
    );
  }
}
