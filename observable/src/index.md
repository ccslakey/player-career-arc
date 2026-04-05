---
title: Career Arc Visualizer
style: styles.css
theme: dashboard
---

```js
import {careerArcChart} from "./components/careerArcChart.js";
import {normalizeDataset} from "./components/normalizeDataset.js";
import {playerPicker} from "./components/playerPicker.js";

const rawDataset = await FileAttachment("data/all_players_history.json").json();
const dataset = normalizeDataset(rawDataset);
const allPlayers = dataset.players;
const metrics = dataset.metadata.metrics;
const defaultPlayers = ["Mike Trout", "Clayton Kershaw", "Mookie Betts"].filter((name) =>
  allPlayers.some((player) => player.name === name)
);
const playerNames = allPlayers.map((player) => player.name);
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
const selectedNames = view(
  playerPicker({
    players: playerNames,
    initialSelectedNames: defaultPlayers,
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
const limitedNames = selectedNames.slice(0, 10);
const activeMetric = metrics.find((metric) => metric.key === selectedMetricKey) ?? metrics[0];
const selectedPlayers = allPlayers.filter((player) => limitedNames.includes(player.name));
```

```js
selectedNames.length > 10
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
html`<p class="note">Notes: ${dataset.metadata.notes.join(" ")}</p>`
```
