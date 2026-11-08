type ProviderConfig = {
  provider?: string;
  config?: {
    model?: string;
    api_key?: string;
    openai_base_url?: string;
    embedding_dims?: number | null;
  };
};

export type EffectiveConfig = {
  llm?: ProviderConfig;
  embedder?: ProviderConfig;
  vector_store?: {
    provider?: string;
    config?: {
      collection_name?: string;
      embedding_model_dims?: number;
      hnsw?: boolean;
    };
  };
};

export const getEffectiveConfig = (data: unknown): EffectiveConfig | null => {
  if (!data || typeof data !== "object") {
    return null;
  }

  const record = data as Record<string, unknown>;
  return (
    (record.effective_config as EffectiveConfig) ||
    (record.config as EffectiveConfig) ||
    (record as EffectiveConfig)
  );
};

export const buildProviderConfig = ({
  provider,
  model,
  apiKey,
  baseUrl,
  embeddingDims,
}: {
  provider: string;
  model: string;
  apiKey?: string;
  baseUrl?: string;
  embeddingDims?: string;
}) => {
  if (!provider) {
    return undefined;
  }

  const key = apiKey?.trim();
  const dimensions = embeddingDims?.trim();
  if (
    dimensions &&
    (!/^\d+$/.test(dimensions) ||
      Number(dimensions) < 1 ||
      !Number.isSafeInteger(Number(dimensions)))
  ) {
    throw new Error("Embedding dimensions must be a positive integer.");
  }
  if (provider === "openai" && baseUrl?.trim()) {
    let url: URL;
    try {
      url = new URL(baseUrl.trim());
    } catch {
      throw new Error("Base URL must be a valid HTTP or HTTPS URL.");
    }
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    ) {
      throw new Error(
        "Base URL must use HTTP or HTTPS without credentials, query parameters, or fragments.",
      );
    }
  }

  return {
    provider,
    config: {
      model: model.trim() || undefined,
      // Redacted values are display-only and must never overwrite saved secrets.
      api_key: key && !/\[redacted\]|\*{3,}|•{3,}/i.test(key) ? key : undefined,
      ...(provider === "openai" && baseUrl !== undefined
        ? { openai_base_url: baseUrl.trim() }
        : {}),
      ...(embeddingDims !== undefined
        ? { embedding_dims: dimensions ? Number(dimensions) : null }
        : {}),
    },
  };
};

export type PgvectorSettings = {
  collectionName: string;
  dimensions: string;
  hnsw: boolean;
};

export const getPgvectorSettings = (
  config: EffectiveConfig | null,
): PgvectorSettings | null => {
  if (config?.vector_store?.provider !== "pgvector") return null;
  const options = config.vector_store.config;
  return {
    collectionName: options?.collection_name ?? "mem0",
    dimensions: String(options?.embedding_model_dims ?? 1536),
    hnsw: options?.hnsw ?? true,
  };
};

export const buildPgvectorConfig = (
  settings: PgvectorSettings | null,
  initial: PgvectorSettings | null,
  embeddingDims?: string,
) => {
  if (!settings) return undefined;
  const collectionName = settings.collectionName.trim();
  const dimensions = settings.dimensions.trim();
  if (!collectionName) throw new Error("Vector collection name is required.");
  if (
    !/^\d+$/.test(dimensions) ||
    Number(dimensions) < 1 ||
    !Number.isSafeInteger(Number(dimensions))
  ) {
    throw new Error("Vector storage dimensions must be a positive integer.");
  }
  const dims = Number(dimensions);
  if (dims > 16000) {
    throw new Error("Vector storage supports at most 16,000 dimensions.");
  }
  if (settings.hnsw && dims > 2000) {
    throw new Error(
      "HNSW supports at most 2,000 dimensions. Disable HNSW for higher dimensions and use a new collection when changing dimensions.",
    );
  }
  if (embeddingDims?.trim() && Number(embeddingDims) !== dims) {
    throw new Error(
      "Embedding API dimensions must match vector storage dimensions.",
    );
  }
  if (
    initial &&
    dims !== Number(initial.dimensions) &&
    collectionName === initial.collectionName.trim()
  ) {
    throw new Error(
      "Changing vector storage dimensions requires a new collection name. Existing data is retained and is not automatically migrated.",
    );
  }
  return {
    provider: "pgvector",
    config: {
      collection_name: collectionName,
      embedding_model_dims: dims,
      hnsw: settings.hnsw,
    },
  };
};
