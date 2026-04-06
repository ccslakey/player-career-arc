# React Parity QA Checklist

Use this checklist to confirm the React app behaves correctly in local development and production.

## Setup

- [ ] Start the React app.

  ```bash
  cd /Users/connorslakey/Desktop/career-arc-visualizer/web
  npm run dev
  ```

- [ ] Open DevTools `Network` and `Console` on the React app.
- [ ] Enable `Disable cache` before reloads.

## Initial Load

- [ ] Hard refresh the app.
- [ ] Confirm React selects Mike Trout, Clayton Kershaw, and Mookie Betts by default.
- [ ] Confirm the default metric is `WAR`.
- [ ] Confirm the chart renders.
- [ ] Confirm the season table renders.
- [ ] Confirm the footer notes render.
- [ ] Confirm `players_manifest.json` loads successfully.
- [ ] Confirm only the three default player history JSON files load on startup.
- [ ] Confirm there are no console errors.

## Player Picker

- [ ] Search by full player name.
- [ ] Search by partial player name.
- [ ] Search by Fangraphs id.
- [ ] Add a fourth player.
- [ ] Remove a selected player.
- [ ] Confirm broad searches only show up to 50 results.
- [ ] Confirm selection is capped at 10 players.

## Metrics

- [ ] Switch through every metric:
- [ ] `Batting Avg`
- [ ] `Home Runs`
- [ ] `RBI`
- [ ] `OPS`
- [ ] `WAR`
- [ ] `ERA`
- [ ] `Strikeouts`
- [ ] `WHIP`
- [ ] Confirm the chart updates for each metric.
- [ ] Confirm the table updates for each metric.
- [ ] Confirm players with missing values do not break the UI.

## Chart And Tooltip

- [ ] Hover several points for each default player.
- [ ] Confirm tooltip shows player name and year.
- [ ] Confirm tooltip shows team and role.
- [ ] Confirm tooltip shows the metric value with the right formatting.
- [ ] Confirm tooltip shows summary text when available.
- [ ] Confirm tooltip shows event annotations when available.
- [ ] Confirm line colors stay stable after interactions.
- [ ] Confirm empty-state messaging is reasonable when a metric has no data.

## URL State

- [ ] Change selected players.
- [ ] Change the metric.
- [ ] Confirm the URL updates.
- [ ] Open the URL in a new tab.
- [ ] Confirm the same players and metric are restored.

## Lazy Loading And Cache

- [ ] Add a new player who was not loaded initially.
- [ ] Confirm only that player history JSON is fetched.
- [ ] Remove and re-add the same player.
- [ ] Confirm the player history is reused from cache instead of refetched.

## Error Handling

- [ ] Temporarily rename one file in `web/public/data/player-history`.
- [ ] Reload and confirm the app shows a readable error state.
- [ ] Restore the file afterward.

## Responsive Checks

- [ ] Test desktop width.
- [ ] Test tablet width.
- [ ] Test narrow mobile width in DevTools.
- [ ] Confirm the picker remains usable.
- [ ] Confirm the chart remains visible.
- [ ] Confirm the table remains readable or scrollable.
- [ ] Confirm tooltips are not entirely off-screen.

## Production Build QA

- [ ] Run the production build.

  ```bash
  cd /Users/connorslakey/Desktop/career-arc-visualizer/web
  npm run build
  npm run preview
  ```

- [ ] Repeat the key checks in production:
- [ ] Initial load
- [ ] Add one new player
- [ ] Metric switching
- [ ] URL state
- [ ] No console errors

## Notes

- [ ] Record any mismatch, bug, or performance concern you find.
- [ ] Convert confirmed issues into board tasks after the pass.
