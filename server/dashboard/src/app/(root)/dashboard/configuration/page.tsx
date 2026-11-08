"use client";

import { useEffect, useState } from "react";
import { RuntimeStatus } from "@/components/self-hosted/runtime-status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "@/components/ui/use-toast";
import { UpgradeBanner } from "@/components/self-hosted/upgrade-banner";
import { getErrorMessage } from "@/lib/error-message";
import { api } from "@/utils/api";
import { MEMORY_ENDPOINTS } from "@/utils/api-endpoints";
import {
  buildProviderConfig,
  getEffectiveConfig,
} from "@/utils/self-hosted-config";
import { useAuth } from "@/hooks/use-auth";
import { useApiQuery } from "@/hooks/use-api-query";

type BundledProviders = {
  llm: string[];
  embedder: string[];
};

export default function ConfigurationPage() {
  const { isAdmin } = useAuth();
  const [isSaving, setIsSaving] = useState(false);
  const [runtimeStatusVersion, setRuntimeStatusVersion] = useState(0);
  const [llmProvider, setLlmProvider] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  const [embedderBaseUrl, setEmbedderBaseUrl] = useState("");
  const [embedderApiKey, setEmbedderApiKey] = useState("");
  const [embeddingDims, setEmbeddingDims] = useState("");
  const [embedderProvider, setEmbedderProvider] = useState("");
  const [embedderModel, setEmbedderModel] = useState("");

  const { data: config, isLoading: isPrefilling } = useApiQuery(
    async () => {
      const res = await api.get(MEMORY_ENDPOINTS.CONFIGURE);
      return getEffectiveConfig(res.data);
    },
    { errorToast: "Failed to load server configuration" },
  );

  const { data: providers } = useApiQuery<BundledProviders>(
    async () => {
      const res = await api.get<BundledProviders>(
        MEMORY_ENDPOINTS.CONFIGURE_PROVIDERS,
      );
      return res.data;
    },
    { errorToast: "Failed to load bundled providers" },
  );

  useEffect(() => {
    if (!config) return;
    setLlmBaseUrl(config.llm?.config?.openai_base_url || "");
    setEmbedderBaseUrl(config.embedder?.config?.openai_base_url || "");
    setEmbeddingDims(config.embedder?.config?.embedding_dims?.toString() || "");
    setLlmProvider((current) => current || config.llm?.provider || "");
    setLlmModel((current) => current || config.llm?.config?.model || "");
    setEmbedderProvider(
      (current) => current || config.embedder?.provider || "",
    );
    setEmbedderModel(
      (current) => current || config.embedder?.config?.model || "",
    );
  }, [config]);

  const handleSave = async () => {
    setIsSaving(true);

    try {
      const llm = buildProviderConfig({
        provider: llmProvider,
        model: llmModel,
        apiKey: llmApiKey,
        baseUrl: llmBaseUrl,
      });
      const embedder = buildProviderConfig({
        provider: embedderProvider,
        model: embedderModel,
        apiKey: embedderApiKey,
        baseUrl: embedderBaseUrl,
        embeddingDims,
      });

      const newConfig: Record<string, unknown> = {
        version: "v1.1",
      };

      if (llm) {
        newConfig.llm = llm;
      }

      if (embedder) {
        newConfig.embedder = embedder;
      }

      await api.post(MEMORY_ENDPOINTS.CONFIGURE, newConfig);
      setLlmApiKey("");
      setEmbedderApiKey("");
      toast({ title: "Configuration saved", variant: "success" });
    } catch (error) {
      toast({
        title: "Failed to save configuration",
        description: getErrorMessage(error),
        variant: "destructive",
      });
    } finally {
      setRuntimeStatusVersion((version) => version + 1);
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold font-fustat">Configuration</h1>
        {isPrefilling && (
          <p className="text-sm text-onSurface-default-tertiary">
            Loading effective server configuration...
          </p>
        )}
      </div>

      <RuntimeStatus key={runtimeStatusVersion} />

      <Card className="border-memBorder-primary">
        <CardHeader>
          <CardTitle className="text-sm">LLM Provider</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Provider</Label>
              <Select
                value={llmProvider}
                onValueChange={(value) => {
                  setLlmProvider(value);
                  setLlmApiKey("");
                  setLlmBaseUrl("");
                }}
                disabled={!isAdmin || !providers}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select provider" />
                </SelectTrigger>
                <SelectContent>
                  {providers?.llm.map((name) => (
                    <SelectItem key={name} value={name}>
                      {name === "openai" ? "OpenAI / OpenAI-compatible" : name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Model</Label>
              <Input
                placeholder="gpt-4.1-nano-2025-04-14"
                value={llmModel}
                onChange={(e) => setLlmModel(e.target.value)}
                disabled={!isAdmin}
              />
            </div>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">API Key</Label>
            <Input
              type="password"
              placeholder="Leave blank to keep existing key"
              autoComplete="new-password"
              value={llmApiKey}
              onChange={(e) => setLlmApiKey(e.target.value)}
              disabled={!isAdmin}
            />
          </div>
          <p className="text-xs text-onSurface-default-tertiary">
            Keys are independent. Leave blank to keep the saved key. Changing
            provider or base URL requires a new key.
          </p>
          {llmProvider === "openai" && (
            <div className="space-y-1">
              <Label htmlFor="llm-base-url">LLM Base URL</Label>
              <Input
                id="llm-base-url"
                type="url"
                value={llmBaseUrl}
                onChange={(e) => setLlmBaseUrl(e.target.value)}
                disabled={!isAdmin}
                placeholder="https://api.openai.com/v1"
              />
              <p className="text-xs text-onSurface-default-tertiary">
                Use the provider&apos;s API root, including /v1 if required.
                Blank uses OpenAI.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-memBorder-primary">
        <CardHeader>
          <CardTitle className="text-sm">Embedding Model</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Provider</Label>
              <Select
                value={embedderProvider}
                onValueChange={(value) => {
                  setEmbedderProvider(value);
                  setEmbedderApiKey("");
                  setEmbedderBaseUrl("");
                }}
                disabled={!isAdmin || !providers}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select provider" />
                </SelectTrigger>
                <SelectContent>
                  {providers?.embedder.map((name) => (
                    <SelectItem key={name} value={name}>
                      {name === "openai" ? "OpenAI / OpenAI-compatible" : name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Model</Label>
              <Input
                placeholder="text-embedding-3-small"
                value={embedderModel}
                onChange={(e) => setEmbedderModel(e.target.value)}
                disabled={!isAdmin}
              />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="embedder-api-key">Embedding API Key</Label>
            <Input
              id="embedder-api-key"
              type="password"
              value={embedderApiKey}
              onChange={(e) => setEmbedderApiKey(e.target.value)}
              disabled={!isAdmin}
              autoComplete="new-password"
              placeholder="Leave blank to keep existing key"
            />
            <p className="text-xs text-onSurface-default-tertiary">
              Separate from the LLM key. Changing provider or base URL requires
              a new key.
            </p>
          </div>
          {embedderProvider === "openai" && (
            <div className="space-y-1">
              <Label htmlFor="embedder-base-url">Embedding Base URL</Label>
              <Input
                id="embedder-base-url"
                type="url"
                value={embedderBaseUrl}
                onChange={(e) => setEmbedderBaseUrl(e.target.value)}
                disabled={!isAdmin}
                placeholder="https://api.openai.com/v1"
              />
              <p className="text-xs text-onSurface-default-tertiary">
                Use the provider&apos;s API root, including /v1 if required.
                Blank uses OpenAI.
              </p>
            </div>
          )}
          <div className="space-y-1">
            <Label htmlFor="embedding-dims">
              Embedding Dimensions (optional)
            </Label>
            <Input
              id="embedding-dims"
              type="number"
              min="1"
              step="1"
              value={embeddingDims}
              onChange={(e) => setEmbeddingDims(e.target.value)}
              disabled={!isAdmin}
              placeholder="Provider default"
            />
            <p className="text-xs text-onSurface-default-tertiary">
              Must match the vector collection. Changing embedding model or
              dimensions may require a new or rebuilt collection. Blank uses the
              provider default. The current pgvector HNSW index supports at most
              2,000 dimensions.
            </p>
          </div>
        </CardContent>
      </Card>

      <p className="text-xs text-onSurface-default-tertiary">
        OpenAI-compatible providers need no additional package. For other
        providers, install their Python package, rebuild the image, and extend
        the bundled list. See the{" "}
        <a
          href="https://docs.mem0.ai/open-source/setup#supported-providers"
          target="_blank"
          rel="noopener noreferrer"
          className="underline underline-offset-4 hover:text-onSurface-default-primary"
        >
          setup guide
        </a>
        .
      </p>

      {isAdmin && (
        <Button
          onClick={handleSave}
          disabled={
            isSaving ||
            isPrefilling ||
            !config ||
            !llmProvider ||
            !embedderProvider
          }
        >
          {isSaving ? "Saving..." : "Save Configuration"}
        </Button>
      )}

      <UpgradeBanner
        id="config-sso"
        message="Looking for SSO / SAML? Available in Enterprise."
        ctaLabel="Contact sales"
        ctaUrl="https://app.mem0.ai/enterprise?utm_source=oss&utm_medium=dashboard-configuration-sso"
        variant="enterprise"
      />
    </div>
  );
}
