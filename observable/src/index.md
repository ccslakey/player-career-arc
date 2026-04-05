---
title: Career Arc Visualizer
style: styles.css
theme: dashboard
---

```js
import {careerArcChart} from "./components/careerArcChart.js";
import {loadSelectedPlayers} from "./components/historyStore.js";
import {playerPicker} from "./components/playerPicker.js";

const manifest = await FileAttachment("data/players_manifest.json").json();
const allPlayers = manifest.players;
const metrics = manifest.metadata.metrics;
const defaultPlayerIds = allPlayers
  .filter((player) => ["Mike Trout", "Clayton Kershaw", "Mookie Betts"].includes(player.n))
  .map((player) => player.i);
const playerOptions = allPlayers.map((player) => ({
  value: player.i,
  label: `${player.n} (${player.y[0]}-${player.y[1]})`,
  searchText: `${player.n} ${player.f ?? ""} ${player.r ?? ""}`
}));
const manifestById = new Map(allPlayers.map((player) => [player.i, player]));
const historyCache = new Map();
const metricOrder = manifest.metadata.metric_order ?? metrics.map((metric) => metric.key);
const defaultPlayers = await loadSelectedPlayers({
  selectedIds: defaultPlayerIds,
  manifestById,
  historyCache,
  metricOrder,
  metrics
});
const notes = manifest.metadata.notes;
const selectionMode = manifest.metadata.selection_mode;
```

```js
const defaultSelectedIds = defaultPlayerIds;
```

<div class="hero">
  <h1>Career arcs, season by season.</h1>
  <p>
    Compare up to 10 MLB players across core batting and pitching stats, then hover any point to see
    season context like team changes, injuries, and generated narrative summaries.
  </p>
</div>

<div class="controls">
  <div class="panel">

```js
const selectedIds = view(
  playerPicker({
    options: playerOptions,
    initialSelectedValues: defaultSelectedIds,
    maxSelections: 10
  })
);
```

  </div>
  <div class="panel">

```js
const selectedMetricKey = view(
  Inputs.select(
    metrics.map((metric) => metric.key),
    {
      label: "Metric",
      value: "war",
      format: (value) => metrics.find((metric) => metric.key === value)?.label ?? value
    }
  )
);
```

  </div>
</div>

```js
const limitedIds = selectedIds.slice(0, 10);
const activeMetric = metrics.find((metric) => metric.key === selectedMetricKey) ?? metrics[0];
const selectedPlayers = await loadSelectedPlayers({
  selectedIds: limitedIds,
  manifestById,
  historyCache,
  metricOrder,
  metrics
});
```

```js
selectedIds.length > 10
  ? html`<div class="warning">Only the first 10 selected players are shown at once.</div>`
  : null
```

```js
careerArcChart({players: selectedPlayers, metric: activeMetric})
```

<div class="panel stat-table">

```js
const rows = selectedPlayers.flatMap((player) =>
  player.seasons
    .filter((season) => season.stats?.[activeMetric.key] != null)
    .map((season) => ({
      player: player.name,
      year: season.year,
      team: season.team,
      role: season.player_type,
      metric: season.stats[activeMetric.key],
      events: (season.events ?? []).map((event) => event.label).join(", "),
      summary: season.summary ?? ""
    }))
);

Inputs.table(rows, {
  columns: ["player", "year", "team", "role", "metric", "events", "summary"]
})
```

</div>

```js
html`<p class="note">Mode: ${selectionMode}. Notes: ${notes.join(" ")}</p>`
```
