"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type { PgvectorSettings } from "@/utils/self-hosted-config";

export function PgvectorSettingsFields({
  value,
  onChange,
  disabled = false,
}: {
  value: PgvectorSettings;
  onChange: (settings: PgvectorSettings) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset
      className="space-y-3 rounded-md border border-memBorder-primary p-3"
      disabled={disabled}
    >
      <legend className="px-1 text-sm font-medium">
        Vector Storage (pgvector)
      </legend>
      <div className="space-y-1">
        <Label htmlFor="vector-collection-name">Collection Name</Label>
        <Input
          id="vector-collection-name"
          value={value.collectionName}
          onChange={(event) =>
            onChange({ ...value, collectionName: event.target.value })
          }
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="vector-storage-dimensions">
          Vector Storage Dimensions
        </Label>
        <Input
          id="vector-storage-dimensions"
          type="number"
          min="1"
          max="16000"
          step="1"
          value={value.dimensions}
          onChange={(event) =>
            onChange({ ...value, dimensions: event.target.value })
          }
        />
        <p className="text-xs text-onSurface-default-tertiary">
          Must match the embedding model&apos;s output. If Embedding API
          Dimensions is set, it must also match this value.
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Switch
          id="vector-hnsw"
          checked={value.hnsw}
          disabled={disabled}
          onCheckedChange={(hnsw) => onChange({ ...value, hnsw })}
        />
        <Label htmlFor="vector-hnsw">Enable HNSW index</Label>
      </div>
      <p className="text-xs text-onSurface-default-tertiary">
        HNSW supports up to 2,000 dimensions; exact search supports up to
        16,000. For 2,048 dimensions, disable HNSW to use exact search and
        choose a new collection name.
      </p>
      <p className="text-xs text-onSurface-default-tertiary">
        Changing storage dimensions requires a new collection name. Existing
        data stays in the old collection; it is not automatically migrated or
        deleted.
      </p>
    </fieldset>
  );
}
