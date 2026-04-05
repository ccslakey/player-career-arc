import type {CompactDatasetPayload, CompactPlayerHistoryPayload, DatasetMetadata, PlayerRecord, SeasonRecord} from "../types";

interface NormalizedDataset {
  metadata: DatasetMetadata;
  players: PlayerRecord[];
}

export function normalizeDataset(rawDataset: CompactDatasetPayload | NormalizedDataset): NormalizedDataset {
  if (!rawDataset?.metadata?.compact) {
    return rawDataset as NormalizedDataset;
  }

  const compactDataset = rawDataset as CompactDatasetPayload;
  const metricOrder =
    compactDataset.metadata.metric_order ??
    (compactDataset.metadata.metrics ?? []).map((metric) => metric.key);

  return {
    metadata: compactDataset.metadata,
    players: (compactDataset.players ?? []).map((player) => ({
      player_key: player.k,
      name: player.n,
      fangraphs_id: player.f,
      seasons: (player.s ?? []).map((season: CompactPlayerHistoryPayload["s"][number]) =>
        normalizeSeason(season, metricOrder)
      )
    }))
  };
}

function normalizeSeason(
  season: CompactPlayerHistoryPayload["s"][number],
  metricOrder: string[]
): SeasonRecord {
  const [year, playerType, team, statValues = [], eventValues = [], summary = ""] = season;

  return {
    year,
    player_type: playerType,
    team,
    stats: Object.fromEntries(metricOrder.map((metricKey, index) => [metricKey, statValues[index] ?? null])),
    events: eventValues.map(([type, label, note]) => ({type, label, note})),
    summary
  };
}
