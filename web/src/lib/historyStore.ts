import {normalizeDataset} from "./normalizeDataset";
import type {
  CompactPlayerHistoryPayload,
  ManifestPayload,
  ManifestPlayerEntry,
  MetricDefinition,
  PlayerRecord
} from "../types";

const MANIFEST_PATH = assetUrl("data/players_manifest.json");

export async function fetchManifest(signal?: AbortSignal): Promise<ManifestPayload> {
  const response = await fetch(MANIFEST_PATH, {signal});
  if (!response.ok) {
    throw new Error(`Failed to load manifest: ${response.status}`);
  }
  return response.json() as Promise<ManifestPayload>;
}

export async function loadSelectedPlayers({
  selectedIds,
  manifestById,
  historyCache,
  metricOrder,
  metrics,
  signal
}: {
  selectedIds: string[];
  manifestById: Map<string, ManifestPlayerEntry>;
  historyCache: Map<string, Promise<PlayerRecord>>;
  metricOrder: string[];
  metrics: MetricDefinition[];
  signal?: AbortSignal;
}): Promise<PlayerRecord[]> {
  const players = await Promise.all(
    selectedIds.map(async (id) => {
      const entry = manifestById.get(id);
      if (!entry) {
        return null;
      }
      return loadPlayerHistory(entry, historyCache, metricOrder, metrics, signal);
    })
  );

  return players.filter(Boolean) as PlayerRecord[];
}

async function loadPlayerHistory(
  entry: ManifestPlayerEntry,
  historyCache: Map<string, Promise<PlayerRecord>>,
  metricOrder: string[],
  metrics: MetricDefinition[],
  signal?: AbortSignal
): Promise<PlayerRecord> {
  if (historyCache.has(entry.i)) {
    return historyCache.get(entry.i)!;
  }

  const request = fetch(historyPath(entry), {signal})
    .then((response) => {
      if (!response.ok) {
        throw new Error(`${response.status}`);
      }
      return response.json() as Promise<CompactPlayerHistoryPayload>;
    })
    .then((payload) => normalizeHistoryPayload(payload, metricOrder, metrics))
    .catch((error: Error) => {
      historyCache.delete(entry.i);
      throw new Error(`Failed to load player history for ${entry.n}: ${error.message}`);
    });

  historyCache.set(entry.i, request);
  return request;
}

function normalizeHistoryPayload(
  payload: CompactPlayerHistoryPayload,
  metricOrder: string[],
  metrics: MetricDefinition[]
): PlayerRecord {
  const wrapped = {
    metadata: {
      compact: true,
      metric_order: metricOrder,
      metrics
    },
    players: [payload]
  };

  return normalizeDataset(wrapped).players[0];
}

function historyPath(entry: ManifestPlayerEntry): string {
  return assetUrl(`data/player-history/${entry.i}.json`);
}

function assetUrl(path: string): string {
  return new URL(path, window.location.origin + import.meta.env.BASE_URL).toString();
}
