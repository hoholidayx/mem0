// Run with Node 22.6+ using: node --experimental-strip-types --test tests/*.test.mjs
import assert from "node:assert/strict";
import test from "node:test";
import {
  buildProviderConfig,
  buildPgvectorConfig,
  getPgvectorSettings,
  getEffectiveConfig,
} from "../src/utils/self-hosted-config.ts";

const serialized = (options) =>
  JSON.parse(JSON.stringify(buildProviderConfig(options)));

test("LLM and embedding endpoints, models, and keys stay independent", () => {
  const llm = serialized({
    provider: "openai",
    model: "custom-chat",
    apiKey: "llm-test-key",
    baseUrl: "https://chat.example/v1",
  });
  const embedder = serialized({
    provider: "openai",
    model: "custom-embed",
    apiKey: "embedding-test-key",
    baseUrl: "http://localhost:8080/v1",
    embeddingDims: "1024",
  });
  assert.deepEqual(llm, {
    provider: "openai",
    config: {
      model: "custom-chat",
      api_key: "llm-test-key",
      openai_base_url: "https://chat.example/v1",
    },
  });
  assert.deepEqual(embedder, {
    provider: "openai",
    config: {
      model: "custom-embed",
      api_key: "embedding-test-key",
      openai_base_url: "http://localhost:8080/v1",
      embedding_dims: 1024,
    },
  });
});

test("blank and masked secrets are omitted rather than overwriting saved keys", () => {
  for (const apiKey of [
    undefined,
    "",
    "  ",
    "[redacted]",
    "[REDACTED]",
    "********",
    "sk-***1234",
    "••••••",
  ]) {
    assert.equal(
      "api_key" in
        serialized({ provider: "openai", model: "custom-chat", apiKey }).config,
      false,
    );
  }
});

test("blank URL explicitly resets OpenAI endpoint, omitted URL preserves it", () => {
  assert.deepEqual(
    serialized({ provider: "openai", model: "chat", baseUrl: " " }).config,
    { model: "chat", openai_base_url: "" },
  );
  assert.equal(
    "openai_base_url" in
      serialized({ provider: "openai", model: "chat" }).config,
    false,
  );
  assert.equal(
    "openai_base_url" in
      serialized({
        provider: "ollama",
        model: "chat",
        baseUrl: "https://unused.example/v1",
      }).config,
    false,
  );
});

test("invalid endpoints and embedded credentials are rejected", () => {
  for (const baseUrl of [
    "not-a-url",
    "ftp://example.com",
    "https://user:password@example.com/v1",
    "https://example.com/v1?api_key=test",
    "https://example.com/v1#fragment",
  ]) {
    assert.throws(
      () => buildProviderConfig({ provider: "openai", model: "chat", baseUrl }),
      /Base URL/,
    );
  }
});

test("dimensions must be a positive safe integer", () => {
  for (const embeddingDims of [
    "0",
    "-1",
    "1.5",
    "abc",
    "1e3",
    "9007199254740992",
  ]) {
    assert.throws(
      () =>
        buildProviderConfig({
          provider: "openai",
          model: "embed",
          embeddingDims,
        }),
      /positive integer/,
    );
  }
});

test("explicit blank dimensions clears the override; omitted dimensions preserves it", () => {
  for (const embeddingDims of ["", "  "]) {
    assert.deepEqual(
      serialized({ provider: "openai", model: "embed", embeddingDims }).config,
      { model: "embed", embedding_dims: null },
    );
  }
  assert.equal(
    "embedding_dims" in
      serialized({ provider: "openai", model: "embed" }).config,
    false,
  );
});

test("effective config round trips independent endpoints and embedding dimensions", () => {
  const config = {
    llm: {
      provider: "openai",
      config: { model: "chat", openai_base_url: "https://chat.example/v1" },
    },
    embedder: {
      provider: "openai",
      config: {
        model: "embed",
        openai_base_url: "https://embed.example/v1",
        embedding_dims: 768,
      },
    },
  };
  for (const input of [config, { config }, { effective_config: config }]) {
    assert.equal(getEffectiveConfig(input), config);
  }
  assert.equal(getEffectiveConfig(null), null);
  assert.equal(buildProviderConfig({ provider: "", model: "chat" }), undefined);
});

test("storage fields load effective pgvector settings without copying credentials", () => {
  assert.deepEqual(
    getPgvectorSettings({
      vector_store: {
        provider: "pgvector",
        config: {
          collection_name: "existing",
          embedding_model_dims: 768,
          hnsw: false,
          password: "synthetic-secret",
        },
      },
    }),
    { collectionName: "existing", dimensions: "768", hnsw: false },
  );
  assert.equal(
    getPgvectorSettings({ vector_store: { provider: "qdrant" } }),
    null,
  );
  assert.equal(buildPgvectorConfig(null, null), undefined);
});

const existingStorage = {
  collectionName: "existing",
  dimensions: "1536",
  hnsw: true,
};

test("unchanged storage preserves collection and sends only editable settings", () => {
  assert.deepEqual(
    buildPgvectorConfig(existingStorage, existingStorage, "1536"),
    {
      provider: "pgvector",
      config: {
        collection_name: "existing",
        embedding_model_dims: 1536,
        hnsw: true,
      },
    },
  );
});

test("storage dimension changes require a new name and API dimensions must agree", () => {
  assert.throws(
    () =>
      buildPgvectorConfig(
        { ...existingStorage, dimensions: "768" },
        existingStorage,
        "768",
      ),
    /new collection name/,
  );
  assert.throws(
    () => buildPgvectorConfig(existingStorage, existingStorage, "768"),
    /must match/,
  );
  const updated = {
    ...existingStorage,
    collectionName: "new-768",
    dimensions: "768",
  };
  assert.equal(
    buildPgvectorConfig(updated, existingStorage, "768").config.collection_name,
    "new-768",
  );
  assert.equal(
    buildPgvectorConfig(updated, existingStorage, "").config
      .embedding_model_dims,
    768,
  );
});

test("2048 dimensions require HNSW disabled and a new collection", () => {
  const settings = {
    ...existingStorage,
    collectionName: "new-2048",
    dimensions: "2048",
  };
  assert.throws(
    () => buildPgvectorConfig(settings, existingStorage, "2048"),
    /HNSW/,
  );
  assert.deepEqual(
    buildPgvectorConfig({ ...settings, hnsw: false }, existingStorage, "2048"),
    {
      provider: "pgvector",
      config: {
        collection_name: "new-2048",
        embedding_model_dims: 2048,
        hnsw: false,
      },
    },
  );
});

test("storage rejects blank names and invalid dimensions", () => {
  assert.throws(
    () =>
      buildPgvectorConfig(
        { ...existingStorage, collectionName: " " },
        existingStorage,
      ),
    /name is required/,
  );
  for (const dimensions of ["", "0", "-1", "1.5", "bad", "9007199254740992"]) {
    assert.throws(
      () =>
        buildPgvectorConfig(
          { ...existingStorage, dimensions },
          existingStorage,
        ),
      /positive integer/,
    );
  }
});

test("exact search storage dimensions cannot exceed 16000", () => {
  assert.throws(
    () =>
      buildPgvectorConfig(
        { collectionName: "new", dimensions: "16001", hnsw: false },
        existingStorage,
      ),
    /16,000/,
  );
  assert.equal(
    buildPgvectorConfig(
      { collectionName: "new", dimensions: "16000", hnsw: false },
      existingStorage,
    ).config.embedding_model_dims,
    16000,
  );
});

test("max tokens defaults to omitted; explicit blank clears cap with null", () => {
  assert.equal(
    "max_tokens" in serialized({ provider: "openai", model: "chat" }).config,
    false,
  );
  for (const maxTokens of ["", " "]) {
    assert.equal(
      serialized({ provider: "openai", model: "chat", maxTokens }).config
        .max_tokens,
      null,
    );
  }
  assert.equal(
    serialized({ provider: "openai", model: "chat", maxTokens: " 4096 " })
      .config.max_tokens,
    4096,
  );
});

test("max tokens must be a positive safe integer", () => {
  for (const maxTokens of [
    "0",
    "-1",
    "1.5",
    "bad",
    "Infinity",
    "9007199254740992",
  ]) {
    assert.throws(
      () =>
        buildProviderConfig({ provider: "openai", model: "chat", maxTokens }),
      /positive integer/,
    );
  }
});
