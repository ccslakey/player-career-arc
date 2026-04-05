export function normalizeDataset(rawDataset) {
  if (!rawDataset?.metadata?.compact) {
    return rawDataset;
  }

  const metricOrder =
    rawDataset.metadata.metric_order ??
    (rawDataset.metadata.metrics ?? []).map((metric) => metric.key);

  return {
    metadata: rawDataset.metadata,
    players: (rawDataset.players ?? []).map((player) => ({
      player_key: player.k,
      name: player.n,
      fangraphs_id: player.f,
      seasons: (player.s ?? []).map((season) => normalizeSeason(season, metricOrder))
    }))
  };
}

function normalizeSeason(season, metricOrder) {
  const [year, playerType, team, statValues = [], eventValues = [], summary = ""] = season;

  return {
    year,
    player_type: playerType,
    team,
    stats: Object.fromEntries(
      metricOrder.map((metricKey, index) => [metricKey, statValues[index] ?? null])
    ),
    events: eventValues.map(([type, label, note]) => ({type, label, note})),
    summary
  };
}
