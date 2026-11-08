"use client";

import { Button } from "@/components/ui/button";
import { useApiQuery } from "@/hooks/use-api-query";
import { api } from "@/utils/api";
import { MEMORY_ENDPOINTS } from "@/utils/api-endpoints";

type RuntimeStatus = {
  status: "needs_configuration" | "initialization_failed" | "ready";
  ready: boolean;
  missing_providers: string[];
  error_code: string | null;
};

export function RuntimeStatus() {
  const { data, isLoading, error, refetch } = useApiQuery<RuntimeStatus>(
    async () => {
      const response = await api.get<RuntimeStatus>(
        MEMORY_ENDPOINTS.CONFIGURE_STATUS,
      );
      return response.data;
    },
  );

  const missingProviders = data?.missing_providers
    .filter((provider) => provider === "llm" || provider === "embedder")
    .map((provider) => (provider === "llm" ? "LLM" : "embedding"))
    .join(" and ");

  return (
    <div
      className="rounded-md border border-memBorder-primary bg-surface-default-secondary p-3 space-y-2"
      role="status"
      aria-live="polite"
    >
      {isLoading ? (
        <p className="text-sm">Checking memory service status...</p>
      ) : error || !data ? (
        <p className="text-sm">
          Could not check memory service status. Refresh to try again.
        </p>
      ) : data.status === "ready" && data.ready ? (
        <p className="text-sm text-onSurface-positive-primary">
          Memory service is ready.
        </p>
      ) : data.status === "needs_configuration" ? (
        <div className="space-y-1">
          <p className="text-sm font-medium">Provider configuration required</p>
          <p className="text-xs text-onSurface-default-tertiary">
            The dashboard is available. Memory operations remain unavailable
            until {missingProviders || "the required providers"} configuration
            is saved and the memory service initializes successfully.
          </p>
        </div>
      ) : (
        <div className="space-y-1">
          <p className="text-sm font-medium text-onSurface-danger-primary">
            Memory service initialization failed
          </p>
          <p className="text-xs text-onSurface-default-tertiary">
            This is an initialization error, not just missing provider
            configuration. Memory operations are unavailable. Check provider and
            database settings and the server logs, then save the corrected
            configuration.
          </p>
        </div>
      )}
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={isLoading}
        onClick={() => void refetch()}
      >
        Refresh status
      </Button>
    </div>
  );
}
