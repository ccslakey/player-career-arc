# Career Arc Visualizer

A starter project for tracking MLB player career arcs with:

- `pybaseball` for player lookup and season-level stat extraction
- a Python normalization pipeline that emits chart-friendly JSON
- an Observable Framework app with D3 for multi-player comparison
- annotation support for team changes and injuries
- a pluggable summary layer for season-by-season narrative blurbs

## What is included

- Player lookup from a full name or explicit Fangraphs / MLBAM identifier
- Unified season records for hitters, pitchers, or two-way players
- Comparison-ready metrics for up to 10 players
- Tooltip annotations for team changes plus optional manually curated injury events
- A sample dataset so the front end can render before live MLB data is fetched

## Project layout

```text
career-arc-visualizer/
├── config/
│   ├── annotations.example.csv
│   └── players.example.csv
├── data/
│   ├── processed/
│   └── raw/
├── observable/
│   ├── package.json
│   ├── observablehq.config.js
│   └── src/
├── scripts/
│   └── build_player_dataset.py
└── src/
    └── career_arc/
```

## Quick start

### 1. Create a virtual environment

```bash
cd /career-arc-visualizer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Build a live dataset

```bash
python scripts/build_player_dataset.py \
  --players config/players.example.csv \
  --annotations config/annotations.example.csv
```

To pull everyone with at least one at-bat or one pitch in a year range:

```bash
python scripts/build_player_dataset.py \
  --all-players \
  --start-year 2020 \
  --end-year 2025 \
  --annotations config/annotations.example.csv
```

This writes:

- `data/processed/players.json`
- `observable/src/data/players.json`

The processed file keeps the full rich dataset. The Observable file is a compact browser-oriented snapshot.

For large front-end datasets, build a manifest plus lazy-loaded player histories:

```bash
python scripts/build_frontend_store.py \
  --input data/processed/all_players_history.json \
  --manifest-output observable/src/data/players_manifest.json \
  --history-dir observable/src/data/player-history
```

### 3. Preview the Observable app

```bash
cd observable
npm install
npm run dev
```

## Data notes

- `pybaseball` is a strong source for player identifiers and season stats.
- Injury history generally needs a supplemental source or manual curation.
- This starter project therefore supports an annotation CSV that can add injury notes, milestones, awards, and context to tooltips.
- All-player mode filters batting rows to `AB >= 1` and pitching rows to at least one pitch, falling back to batters faced or innings pitched if needed.
- The Observable export is compacted to reduce transfer and disk size for front-end use.
- For large player pools, the recommended front-end setup is a manifest plus per-player lazy-loaded history files.

## Player config schema

`config/players.example.csv`

- `player_name`: full display name
- `fangraphs_id`: optional explicit Fangraphs id
- `mlbam_id`: optional explicit MLBAM id
- `start_year`: optional lower bound
- `end_year`: optional upper bound

## Annotation schema

`config/annotations.example.csv`

- `player_name`
- `year`
- `event_type`
- `label`
- `note`

## Summary generation

The starter ships with a deterministic fallback summarizer so the pipeline is usable immediately.
The code also exposes a prompt-building hook in `src/career_arc/summaries.py` so we can drop in an LLM-backed summary provider later without reshaping the rest of the pipeline.
