import type {
  CompactDatasetPayload,
  CompactEventRow,
  CompactPlayerHistoryPayload,
  DatasetMetadata,
  EventAnnotation,
  PlayerRecord,
  SeasonRecord
} from "../types";

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
    events: eventValues.map((eventValue) => normalizeEvent(eventValue)),
    summary
  };
}

function normalizeEvent(eventValue: CompactEventRow | EventAnnotation): EventAnnotation {
  if (Array.isArray(eventValue)) {
    const [type, label, note, event_date, source, source_url, event_id] = eventValue;
    return {
      type: type ?? null,
      label: label ?? null,
      note: note ?? null,
      event_date: event_date ?? null,
      source: source ?? null,
      source_url: source_url ?? null,
      event_id: event_id ?? null
    };
  }

  return {
    type: eventValue?.type ?? null,
    label: eventValue?.label ?? null,
    note: eventValue?.note ?? null,
    event_date: eventValue?.event_date ?? null,
    source: eventValue?.source ?? null,
    source_url: eventValue?.source_url ?? null,
    event_id: eventValue?.event_id ?? null
  };
}
