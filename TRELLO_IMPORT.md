# Trello Board Import

Board title: `Career Arc Visualizer`

Create these lists in Trello:

1. `Backlog`
2. `Next`
3. `In Progress`
4. `Blocked`
5. `Done`
6. `Definition Of Done`

Then paste each block below into the matching Trello list. In Trello, each new line becomes a new card.

## Backlog

```text
Add career-threshold pruning controls for the front-end dataset.
Add optional era filters and saved comparison presets.
Add richer event annotations beyond team changes and manual injury notes.
Add LLM-backed season summaries behind a provider interface.
Add export/share features for chart views.
Add user-facing methodology notes for metric definitions and data caveats.
```

## Next

```text
Scaffold a React + TypeScript front end, likely with Vite.
Reuse the current manifest plus lazy-loaded player-history JSON contract in the React app.
Port the D3 career arc chart into a React component without changing the underlying visual model.
Build a searchable player picker in React with the same 10-player selection cap.
Add loading, empty, and fetch-error states for manifest and player-history requests.
Add URL state for selected players and active metric so views are shareable.
Add a production hosting target for the React app.
Add screenshots and demo-first positioning to the project README.
```

## In Progress

```text
Evaluate whether the portfolio version should stay in Observable or move fully to React.
```

## Blocked

```text
None currently.
```

## Done

```text
Built the Python data pipeline around pybaseball.
Added player lookup and season normalization for hitters, pitchers, and two-way players.
Added event annotation support for team changes and manual injury/context notes.
Added deterministic fallback season summaries.
Built the Observable proof-of-concept with D3 charting.
Added support for comparing up to 10 players.
Switched the front end to a searchable player picker.
Added all-player historical dataset generation.
Reworked Fangraphs fetching to run year-by-year instead of oversized multi-decade requests.
Added a manifest plus lazy-loaded per-player history architecture for front-end performance.
Added in-memory caching for player history fetches.
Limited search results to the top 50 matches in the picker.
Trimmed the front-end manifest to reduce startup payload size.
Patched the production build so lazy-loaded player-history files are included in dist.
```

## Definition Of Done

```text
React app is the primary front end.
Production build loads only the manifest plus selected player histories on first render.
Core chart interactions are stable on desktop and mobile.
Automated tests cover the pipeline and key front-end behavior.
CI runs tests and production build on every push.
Hosted demo is live and linked prominently in the README.
```
