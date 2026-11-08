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
