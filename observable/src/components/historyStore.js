import {normalizeDataset} from "./normalizeDataset.js";

export async function loadSelectedPlayers({
  selectedIds,
  manifestById,
  historyCache,
  metricOrder,
  metrics
}) {
  const players = await Promise.all(
    selectedIds.map(async (id) => {
      const entry = manifestById.get(id);
      if (!entry) return null;
      return loadPlayerHistory(entry, historyCache, metricOrder, metrics);
    })
  );
  return players.filter(Boolean);
}

async function loadPlayerHistory(entry, historyCache, metricOrder, metrics) {
  if (historyCache.has(entry.i)) {
    return historyCache.get(entry.i);
  }

  if (!entry.i) {
    throw new Error(`Missing player history id for ${entry.n}.`);
  }

  const request = fetch(resolveHistoryUrl(historyPath(entry)))
    .then((response) => {
      if (!response.ok) {
        throw new Error(`${response.status}`);
      }
      return response.json();
    })
    .then((payload) => normalizeHistoryPayload(payload, metricOrder, metrics))
    .catch((error) => {
      historyCache.delete(entry.i);
      throw new Error(`Failed to load player history for ${entry.n}: ${error.message}`);
    });

  historyCache.set(entry.i, request);
  return request;
}

function normalizeHistoryPayload(payload, metricOrder, metrics) {
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

function resolveHistoryUrl(path) {
  return new URL(path, document.baseURI);
}

function historyPath(entry) {
  if (entry.h) return entry.h;
  return `./_file/data/player-history/${entry.i}.json`;
}
