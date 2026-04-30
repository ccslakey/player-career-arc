from __future__ import annotations

import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .annotations import (
    fetch_bulk_transaction_injury_events,
    fetch_transaction_injury_events,
    infer_team_change_events,
    load_annotation_index,
    merge_annotation_events,
)
from .lookup import PlayerRequest, resolve_player
from .summaries import generate_fallback_summary


METRICS = [
    {"key": "avg", "label": "Batting Avg", "format": "average"},
    {"key": "hr", "label": "Home Runs", "format": "integer"},
    {"key": "rbi", "label": "RBI", "format": "integer"},
    {"key": "ops", "label": "OPS", "format": "average"},
    {"key": "war", "label": "WAR", "format": "decimal"},
    {"key": "era", "label": "ERA", "format": "average"},
    {"key": "strikeouts", "label": "Strikeouts", "format": "integer"},
    {"key": "whip", "label": "WHIP", "format": "average"},
]

STAT_ALIASES = {
    "year": ["Season", "season", "year"],
    "team": ["Team", "Tm", "team"],
    "name": ["PlayerName", "Name", "name"],
    "fangraphs_id": ["mlbID", "playerid", "IDfg", "key_fangraphs", "fangraphs_id"],
    "avg": ["AVG", "BA", "avg"],
    "hr": ["HR", "hr"],
    "rbi": ["RBI", "rbi"],
    "ops": ["OPS", "ops"],
    "war": ["WAR", "war"],
    "era": ["ERA", "era"],
    "strikeouts": ["SO", "K", "strikeouts"],
    "whip": ["WHIP", "whip"],
}


def build_dataset(
    players_csv: str | Path | None,
    annotations_csv: str | Path | None,
    processed_output: str | Path,
    frontend_output: str | Path,
    include_all_players: bool = False,
    start_year: int | None = None,
    end_year: int | None = None,
) -> dict[str, object]:
    annotation_index = load_annotation_index(annotations_csv)
    if include_all_players:
        start_year = start_year or 2000
        end_year = end_year or datetime.now().year
        batting_rows, pitching_rows = load_pybaseball_tables(start_year, end_year)
        players = build_all_players_dataset(
            batting_rows=batting_rows,
            pitching_rows=pitching_rows,
            annotation_index=annotation_index,
            start_year=start_year,
            end_year=end_year,
        )
    else:
        if players_csv is None:
            raise ValueError("players_csv is required unless include_all_players=True.")

        player_requests = load_player_requests(players_csv)
        resolved_players = [resolve_player(request) for request in player_requests]
        start_year, end_year = determine_year_range(resolved_players)
        batting_rows, pitching_rows = load_pybaseball_tables(start_year, end_year)

        players = []
        for resolved in resolved_players:
            if resolved.fangraphs_id is None:
                raise ValueError(
                    f"Could not resolve a Fangraphs id for {resolved.player_name!r}. "
                    "Provide a Fangraphs id directly or use a full name that pybaseball can disambiguate."
                )
            seasons = build_player_seasons(
                resolved.player_name,
                resolved.fangraphs_id,
                resolved.mlbam_id,
                batting_rows,
                pitching_rows,
                annotation_index,
                resolved.start_year or start_year,
                resolved.end_year or end_year,
            )
            players.append(
                {
                    "player_key": slugify(resolved.player_name),
                    "name": resolved.player_name,
                    "fangraphs_id": resolved.fangraphs_id,
                    "mlbam_id": resolved.mlbam_id,
                    "seasons": seasons,
                }
            )

    dataset = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "pybaseball",
            "selection_mode": "all_players" if include_all_players else "configured_players",
            "start_year": start_year,
            "end_year": end_year,
            "metrics": METRICS,
            "notes": [
                "Team-change events are inferred season to season from the player team field.",
                "Injury notes and other context can be added through the annotation CSV.",
                "Strikeouts mean batter strikeouts for hitters and pitcher strikeouts for pitchers.",
                "All-player mode includes anyone with at least one at-bat or one pitch in the selected year range.",
            ],
        },
        "players": players,
    }

    write_json(processed_output, dataset)
    write_json(frontend_output, build_frontend_snapshot(dataset))
    return dataset


def apply_annotations_to_dataset(
    dataset_input: str | Path,
    annotations_csv: str | Path | None,
    processed_output: str | Path,
    frontend_output: str | Path,
    verbose: bool = False,
) -> dict[str, object]:
    dataset_path = Path(dataset_input)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset input not found: {dataset_path}")

    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(dataset, dict):
        raise ValueError("Dataset input must be a JSON object.")

    annotation_index = load_annotation_index(annotations_csv)
    players = dataset.get("players")
    log = print if verbose else None
    if isinstance(players, list):
        if log is not None:
            log(f"[annotations] Loaded {len(players)} players from {dataset_path}.")

        annotatable_players = 0
        players_with_mlbam = 0
        min_year: int | None = None
        max_year: int | None = None
        mlbam_ids: set[int] = set()
        for player in players:
            if not isinstance(player, dict):
                continue
            player_name = str(player.get("name") or "").strip()
            seasons = player.get("seasons")
            if not player_name or not isinstance(seasons, list):
                continue

            annotatable_players += 1
            season_years = [year for year in (_coerce_int(season.get("year")) for season in seasons) if year is not None]
            if season_years:
                player_min = min(season_years)
                player_max = max(season_years)
                min_year = player_min if min_year is None else min(min_year, player_min)
                max_year = player_max if max_year is None else max(max_year, player_max)

            mlbam_id = _coerce_int(player.get("mlbam_id"))
            if mlbam_id is not None:
                players_with_mlbam += 1
                mlbam_ids.add(mlbam_id)

        if log is not None:
            log(
                f"[annotations] Annotating {annotatable_players} players "
                f"({players_with_mlbam} with MLBAM ids)."
            )

        prefetched_injuries: dict[int, list[dict[str, object]]] = {}
        if mlbam_ids and min_year is not None and max_year is not None:
            if log is not None:
                log(
                    "[annotations] Prefetching MLB transaction injuries "
                    f"for {len(mlbam_ids)} players across {min_year}-{max_year}."
                )
            prefetched_injuries, fetch_stats = fetch_bulk_transaction_injury_events(
                mlbam_ids=mlbam_ids,
                start_year=min_year,
                end_year=max_year,
                progress_logger=log,
            )
            if log is not None:
                log(
                    "[annotations] Injury prefetch summary: "
                    f"years={fetch_stats.years_succeeded}/{fetch_stats.years_requested} succeeded, "
                    f"failed={fetch_stats.years_failed}, "
                    f"transactions_scanned={fetch_stats.transactions_scanned}, "
                    f"target_player_transactions={fetch_stats.transactions_for_target_players}, "
                    f"injury_events={fetch_stats.injury_events_emitted}."
                )
        elif log is not None:
            log("[annotations] Skipping injury prefetch (no eligible MLBAM ids/year range).")

        progress_start = time.monotonic()
        progress_processed = 0
        for player in players:
            if not isinstance(player, dict):
                continue

            player_name = str(player.get("name") or "").strip()
            if not player_name:
                continue

            seasons = player.get("seasons")
            if not isinstance(seasons, list):
                continue

            seasons.sort(key=_season_sort_key)
            mlbam_id = _coerce_int(player.get("mlbam_id"))
            enrich_seasons_with_annotations(
                player_name=player_name,
                seasons=seasons,
                annotation_index=annotation_index,
                player_id=player_history_id(player),
                mlbam_id=mlbam_id,
                prefetched_injury_events=prefetched_injuries.get(mlbam_id, []),
            )
            progress_processed += 1
            if log is not None:
                _print_progress(
                    prefix="Player annotations",
                    current=progress_processed,
                    total=annotatable_players,
                    started_at=progress_start,
                )
        if log is not None and annotatable_players:
            _finish_progress()

    metadata = dataset.get("metadata")
    if isinstance(metadata, dict):
        metadata["generated_at"] = datetime.now(timezone.utc).isoformat()

    write_json(processed_output, dataset)
    write_json(frontend_output, build_frontend_snapshot(dataset))
    return dataset


def load_player_requests(path: str | Path) -> list[PlayerRequest]:
    requests: list[PlayerRequest] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            player_name = (row.get("player_name") or "").strip()
            if not player_name:
                continue

            requests.append(
                PlayerRequest(
                    player_name=player_name,
                    fangraphs_id=_coerce_int(row.get("fangraphs_id")),
                    mlbam_id=_coerce_int(row.get("mlbam_id")),
                    start_year=_coerce_int(row.get("start_year")),
                    end_year=_coerce_int(row.get("end_year")),
                )
            )
    return requests


def determine_year_range(players: list[object]) -> tuple[int, int]:
    start_years = [player.start_year for player in players if getattr(player, "start_year", None)]
    end_years = [player.end_year for player in players if getattr(player, "end_year", None)]
    current_year = datetime.now().year
    return min(start_years or [2000]), max(end_years or [current_year])


def _build_war_lookup(war_frame) -> dict[tuple[int, int], float]:
    """Aggregate multi-stint WAR rows into a single (mlb_id, year) -> WAR dict."""
    valid = war_frame.dropna(subset=["mlb_ID", "year_ID"])
    totals = valid.groupby(["mlb_ID", "year_ID"])["WAR"].sum()
    return {(int(mlb_id), int(year)): float(war) for (mlb_id, year), war in totals.items()}


BREF_RANGE_MIN_YEAR = 2008


def load_pybaseball_tables(start_year: int = 1900, end_year: int = datetime.now().year) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    from pybaseball import cache

    cache.enable()

    needs_bref_lookup = end_year >= BREF_RANGE_MIN_YEAR
    bat_war_lookup: dict[tuple[int, int], float] = {}
    pitch_war_lookup: dict[tuple[int, int], float] = {}
    if needs_bref_lookup:
        from pybaseball import batting_stats_bref, bwar_bat, bwar_pitch, pitching_stats_bref
        print("Loading Baseball Reference WAR tables...")
        bat_war_lookup = _build_war_lookup(bwar_bat())
        pitch_war_lookup = _build_war_lookup(bwar_pitch())

    batting_rows: list[dict[str, object]] = []
    pitching_rows: list[dict[str, object]] = []

    bref_scrape_cache = Path(cache.config.cache_directory) / "career-arc-bref"

    for year in range(start_year, end_year + 1):
        if year < BREF_RANGE_MIN_YEAR:
            batting_rows.extend(_load_pre_2008_year(year, "batting", bref_scrape_cache))
            pitching_rows.extend(_load_pre_2008_year(year, "pitching", bref_scrape_cache))
            continue

        print(f"Loading Baseball Reference batting data for {year}")
        batting_frame = batting_stats_bref(year)
        if batting_frame is not None and not batting_frame.empty:
            batting_frame = batting_frame[batting_frame["Lev"].str.startswith("Maj", na=False)].copy()
            batting_frame["Season"] = year
            rows = batting_frame.to_dict(orient="records")
            for row in rows:
                mlb_id = row.get("mlbID")
                if mlb_id is not None:
                    row["WAR"] = bat_war_lookup.get((int(mlb_id), year))
                _normalize_row(row)
            batting_rows.extend(rows)

        print(f"Loading Baseball Reference pitching data for {year}")
        pitching_frame = pitching_stats_bref(year)
        if pitching_frame is not None and not pitching_frame.empty:
            pitching_frame = pitching_frame[pitching_frame["Lev"].str.startswith("Maj", na=False)].copy()
            pitching_frame["Season"] = year
            rows = pitching_frame.to_dict(orient="records")
            for row in rows:
                mlb_id = row.get("mlbID")
                if mlb_id is not None:
                    row["WAR"] = pitch_war_lookup.get((int(mlb_id), year))
                _normalize_row(row)
            pitching_rows.extend(rows)

    return batting_rows, pitching_rows


def _load_pre_2008_year(year: int, stat_type: str, cache_dir: Path) -> list[dict[str, object]]:
    """Scrape a single pre-2008 season directly from baseball-reference.com.

    pybaseball's batting_stats_bref / pitching_stats_bref refuse years before
    2008, so we hit the season's standard-batting / standard-pitching page
    ourselves. The bref_scrape module honors Crawl-delay: 3 and caches
    pages on disk so re-runs don't re-fetch.
    """
    from .bref_scrape import attach_mlb_ids, scrape_bref_season

    print(f"Loading Baseball Reference {stat_type} data for {year} (direct scrape)")
    rows = scrape_bref_season(year, stat_type, cache_dir)
    attach_mlb_ids(rows)
    for row in rows:
        _normalize_row(row)
    return rows


def build_all_players_dataset(
    batting_rows: list[dict[str, object]],
    pitching_rows: list[dict[str, object]],
    annotation_index: dict[tuple[str, int], list[object]],
    start_year: int,
    end_year: int,
) -> list[dict[str, object]]:
    grouped_players = group_rows_by_player(
        batting_rows=batting_rows,
        pitching_rows=pitching_rows,
        start_year=start_year,
        end_year=end_year,
    )
    players: list[dict[str, object]] = []

    for fangraphs_id, grouped in sorted(grouped_players.items(), key=lambda item: item[1]["name"]):
        seasons = build_player_seasons_from_rows(
            player_name=grouped["name"],
            batting_rows=grouped["batting"],
            pitching_rows=grouped["pitching"],
            annotation_index=annotation_index,
            player_id=f"fg-{fangraphs_id}",
            mlbam_id=None,
        )
        if not seasons:
            continue

        players.append(
            {
                "player_key": slugify(grouped["name"]),
                "name": grouped["name"],
                "fangraphs_id": fangraphs_id,
                "mlbam_id": None,
                "seasons": seasons,
            }
        )

    return players


def group_rows_by_player(
    batting_rows: list[dict[str, object]],
    pitching_rows: list[dict[str, object]],
    start_year: int,
    end_year: int,
) -> dict[int, dict[str, object]]:
    grouped: dict[int, dict[str, object]] = {}

    for stat_type, rows in (("batting", batting_rows), ("pitching", pitching_rows)):
        for row in rows:
            if not row_matches_filters(
                row=row,
                fangraphs_id=None,
                start_year=start_year,
                end_year=end_year,
                stat_type=stat_type,
            ):
                continue

            row_player_id = _coerce_int(_pick(row, "fangraphs_id"))
            player_name = _pick(row, "name")
            if row_player_id is None or not isinstance(player_name, str) or not player_name:
                continue

            grouped.setdefault(
                row_player_id,
                {"name": player_name, "batting": [], "pitching": [], "latest_year": start_year},
            )
            if stat_type == "batting":
                grouped[row_player_id]["batting"].append(row)
            else:
                grouped[row_player_id]["pitching"].append(row)

            row_year = _coerce_int(_pick(row, "year"))
            if row_year is not None and row_year >= grouped[row_player_id]["latest_year"]:
                grouped[row_player_id]["name"] = player_name
                grouped[row_player_id]["latest_year"] = row_year

    return grouped


def build_player_seasons(
    player_name: str,
    fangraphs_id: int,
    mlbam_id: int | None,
    batting_rows: list[dict[str, object]],
    pitching_rows: list[dict[str, object]],
    annotation_index: dict[tuple[str, int], list[object]],
    start_year: int,
    end_year: int,
) -> list[dict[str, object]]:
    batting = filter_player_rows(batting_rows, fangraphs_id, start_year, end_year, "batting")
    pitching = filter_player_rows(pitching_rows, fangraphs_id, start_year, end_year, "pitching")
    return build_player_seasons_from_rows(
        player_name=player_name,
        batting_rows=batting,
        pitching_rows=pitching,
        annotation_index=annotation_index,
        player_id=f"fg-{fangraphs_id}",
        mlbam_id=mlbam_id,
    )


def build_player_seasons_from_rows(
    player_name: str,
    batting_rows: list[dict[str, object]],
    pitching_rows: list[dict[str, object]],
    annotation_index: dict[tuple[str, int], list[object]],
    player_id: str | None = None,
    mlbam_id: int | None = None,
) -> list[dict[str, object]]:
    batting = batting_rows
    pitching = pitching_rows

    by_year: dict[int, dict[str, object]] = {}
    for row in batting:
        year = _coerce_int(_pick(row, "year"))
        if year is None:
            continue
        by_year.setdefault(year, {})
        by_year[year]["batting"] = row
    for row in pitching:
        year = _coerce_int(_pick(row, "year"))
        if year is None:
            continue
        by_year.setdefault(year, {})
        by_year[year]["pitching"] = row

    seasons: list[dict[str, object]] = []
    for year in sorted(by_year):
        bundle = by_year[year]
        batting_row = bundle.get("batting")
        pitching_row = bundle.get("pitching")
        season = normalize_season(player_name, year, batting_row, pitching_row)
        seasons.append(season)

    if not seasons:
        return []

    season_years = [season["year"] for season in seasons if isinstance(season.get("year"), int)]
    if not season_years:
        return seasons
    enrich_seasons_with_annotations(
        player_name=player_name,
        seasons=seasons,
        annotation_index=annotation_index,
        player_id=player_id,
        mlbam_id=mlbam_id,
    )
    return seasons


def enrich_seasons_with_annotations(
    player_name: str,
    seasons: list[dict[str, object]],
    annotation_index: dict[tuple[str, int], list[object]],
    player_id: str | None,
    mlbam_id: int | None,
    prefetched_injury_events: list[dict[str, object]] | None = None,
) -> None:
    season_years = [season["year"] for season in seasons if isinstance(season.get("year"), int)]
    if not season_years:
        for season in seasons:
            season["events"] = []
            season["summary"] = generate_fallback_summary(player_name, season)
        return

    if prefetched_injury_events is not None:
        injury_events = list(prefetched_injury_events)
    else:
        injury_events = fetch_transaction_injury_events(
            mlbam_id=mlbam_id,
            start_year=min(season_years),
            end_year=max(season_years),
        )
    inferred_events = infer_team_change_events(seasons)
    injury_events_by_year = index_events_by_year(injury_events)
    inferred_events_by_year = index_events_by_year(inferred_events)
    dedupe_player_id = player_id or slugify(player_name)

    for season in seasons:
        year = _coerce_int(season.get("year"))
        if year is None:
            continue

        candidates: list[dict[str, object]] = []
        candidates.extend(injury_events_by_year.get(year, []))
        candidates.extend(inferred_events_by_year.get(year, []))
        candidates.extend(manual_events_for_year(annotation_index, player_name, year))

        season["events"] = merge_annotation_events(
            player_id=dedupe_player_id,
            year=year,
            candidate_events=candidates,
        )
        season["summary"] = generate_fallback_summary(player_name, season)


def manual_events_for_year(
    annotation_index: dict[tuple[str, int], list[object]],
    player_name: str,
    year: int,
) -> list[dict[str, object]]:
    key = (player_name.lower(), year)
    manual_events = annotation_index.get(key, [])
    converted: list[dict[str, object]] = []
    for manual_event in manual_events:
        if hasattr(manual_event, "to_dict"):
            payload = manual_event.to_dict()
        elif isinstance(manual_event, dict):
            payload = dict(manual_event)
        else:
            continue

        if isinstance(payload, dict):
            event_payload = dict(payload)
            event_payload.setdefault("year", year)
            converted.append(event_payload)
    return converted


def index_events_by_year(events: list[dict[str, object]]) -> dict[int, list[dict[str, object]]]:
    by_year: dict[int, list[dict[str, object]]] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        year = _coerce_int(event.get("year"))
        if year is None:
            continue
        by_year.setdefault(year, []).append(event)
    return by_year


def filter_player_rows(
    rows: list[dict[str, object]],
    fangraphs_id: int | None,
    start_year: int,
    end_year: int,
    stat_type: str,
) -> list[dict[str, object]]:
    filtered = []
    for row in rows:
        if row_matches_filters(row, fangraphs_id, start_year, end_year, stat_type):
            filtered.append(row)
    return filtered


def row_matches_filters(
    row: dict[str, object],
    fangraphs_id: int | None,
    start_year: int,
    end_year: int,
    stat_type: str,
) -> bool:
    row_player_id = _coerce_int(_pick(row, "fangraphs_id"))
    year = _coerce_int(_pick(row, "year"))
    if year is None or row_player_id is None:
        return False
    if fangraphs_id is not None and row_player_id != fangraphs_id:
        return False
    if year < start_year or year > end_year:
        return False
    if stat_type == "batting":
        return row_has_batting_activity(row)
    if stat_type == "pitching":
        return row_has_pitching_activity(row)
    raise ValueError(f"Unknown stat_type: {stat_type}")


def _print_progress(prefix: str, current: int, total: int, started_at: float) -> None:
    if total <= 0:
        return

    elapsed = max(time.monotonic() - started_at, 0.001)
    rate = current / elapsed
    percent = (current / total) * 100

    if sys.stdout.isatty():
        width = 28
        filled = int(width * current / total)
        bar = "#" * filled + "-" * (width - filled)
        print(
            f"\r[{prefix}] [{bar}] {current}/{total} ({percent:5.1f}%) "
            f"{rate:5.1f} players/s",
            end="",
            flush=True,
        )
        return

    if current == total or current % 500 == 0:
        print(
            f"[{prefix}] {current}/{total} ({percent:5.1f}%) "
            f"{rate:5.1f} players/s"
        )


def _finish_progress() -> None:
    if sys.stdout.isatty():
        print()


def row_has_batting_activity(row: dict[str, object]) -> bool:
    at_bats = _coerce_int(_pick_optional(row, ["AB", "ab"]))
    return at_bats is not None and at_bats >= 1


def row_has_pitching_activity(row: dict[str, object]) -> bool:
    pitches = _coerce_int(_pick_optional(row, ["Pitches", "pitches"]))
    if pitches is not None:
        return pitches >= 1

    batters_faced = _coerce_int(_pick_optional(row, ["TBF", "BF", "batters_faced"]))
    if batters_faced is not None:
        return batters_faced >= 1

    innings_pitched = _coerce_float(_pick_optional(row, ["IP", "ip"]))
    return innings_pitched is not None and innings_pitched > 0


def normalize_season(
    player_name: str,
    year: int,
    batting_row: dict[str, object] | None,
    pitching_row: dict[str, object] | None,
) -> dict[str, object]:
    player_type = "two_way" if batting_row and pitching_row else "pitcher" if pitching_row else "hitter"
    source_row = batting_row or pitching_row or {}
    team = _pick(source_row, "team") or "Unknown"

    stats = {
        "avg": _coerce_float(_pick(batting_row, "avg")) if batting_row else None,
        "hr": _coerce_int(_pick(batting_row, "hr")) if batting_row else None,
        "rbi": _coerce_int(_pick(batting_row, "rbi")) if batting_row else None,
        "ops": _coerce_float(_pick(batting_row, "ops")) if batting_row else None,
        "war": _sum_nullable(
            _coerce_float(_pick(batting_row, "war")),
            _coerce_float(_pick(pitching_row, "war")),
        ),
        "era": _coerce_float(_pick(pitching_row, "era")) if pitching_row else None,
        "strikeouts": _coerce_int(_pick(pitching_row, "strikeouts"))
        if pitching_row
        else _coerce_int(_pick(batting_row, "strikeouts"))
        if batting_row
        else None,
        "whip": _coerce_float(_pick(pitching_row, "whip")) if pitching_row else None,
    }

    teams = []
    if isinstance(team, str) and team:
        teams.append(team)

    return {
        "player_name": player_name,
        "year": year,
        "player_type": player_type,
        "team": team,
        "teams": teams,
        "stats": stats,
        "events": [],
        "summary": "",
    }


def write_json(path: str | Path, payload: dict[str, object], compact: bool = False) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    output_path.write_text(serialized, encoding="utf-8")


def build_frontend_snapshot(dataset: dict[str, object]) -> dict[str, object]:
    metadata = dataset.get("metadata", {})
    players = dataset.get("players", [])
    metric_order = [metric["key"] for metric in METRICS]

    compact_players = []
    if isinstance(players, list):
        for player in players:
            if not isinstance(player, dict):
                continue
            seasons = player.get("seasons", [])
            compact_players.append(
                {
                    "k": player.get("player_key"),
                    "n": player.get("name"),
                    "f": player.get("fangraphs_id"),
                    "s": compact_seasons(seasons, metric_order),
                }
            )

    compact_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    compact_metadata["compact"] = True
    compact_metadata["metric_order"] = metric_order

    return {
        "metadata": compact_metadata,
        "players": compact_players,
    }


def build_history_manifest(dataset: dict[str, object]) -> dict[str, object]:
    metadata = dataset.get("metadata", {})
    players = dataset.get("players", [])

    manifest_players = []
    if isinstance(players, list):
        for player in players:
            if not isinstance(player, dict):
                continue
            seasons = player.get("seasons", [])
            if not isinstance(seasons, list) or not seasons:
                continue

            first_year = min(season.get("year") for season in seasons if isinstance(season, dict) and isinstance(season.get("year"), int))
            last_year = max(season.get("year") for season in seasons if isinstance(season, dict) and isinstance(season.get("year"), int))
            player_type = infer_manifest_player_type(seasons)
            history_id = player_history_id(player)

            manifest_players.append(
                {
                    "i": history_id,
                    "n": player.get("name"),
                    "f": player.get("fangraphs_id"),
                    "y": [first_year, last_year],
                    "r": player_type,
                }
            )

    manifest_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    manifest_metadata["manifest"] = True
    return {
        "metadata": manifest_metadata,
        "players": manifest_players,
    }


def build_player_history_payload(player: dict[str, object], metric_order: list[str]) -> dict[str, object]:
    return {
        "k": player.get("player_key"),
        "n": player.get("name"),
        "f": player.get("fangraphs_id"),
        "s": compact_seasons(player.get("seasons"), metric_order, include_summary=True),
    }


def build_history_store(
    dataset: dict[str, object],
    manifest_output: str | Path,
    history_dir: str | Path,
) -> dict[str, object]:
    metric_order = [metric["key"] for metric in METRICS]
    manifest = build_history_manifest(dataset)
    history_path = Path(history_dir)
    history_path.mkdir(parents=True, exist_ok=True)

    players = dataset.get("players", [])
    if isinstance(players, list):
        for player in players:
            if not isinstance(player, dict):
                continue
            history_id = player_history_id(player)
            payload = build_player_history_payload(player, metric_order)
            write_json(history_path / f"{history_id}.json", payload, compact=True)

    write_json(manifest_output, manifest, compact=True)
    return manifest


def compact_seasons(
    seasons: object,
    metric_order: list[str],
    include_summary: bool = False,
) -> list[list[object]]:
    compact: list[list[object]] = []
    if not isinstance(seasons, list):
        return compact

    for season in seasons:
        if not isinstance(season, dict):
            continue
        stats = season.get("stats", {})
        events = season.get("events", [])
        row = [
            season.get("year"),
            season.get("player_type"),
            season.get("team"),
            compact_stats(stats, metric_order),
            compact_events(events),
        ]
        if include_summary:
            row.append(season.get("summary"))
        compact.append(row)
    return compact


def compact_stats(stats: object, metric_order: list[str]) -> list[object]:
    if not isinstance(stats, dict):
        return [None for _ in metric_order]
    return [stats.get(metric_key) for metric_key in metric_order]


def compact_events(events: object) -> list[list[object]]:
    compact: list[list[object]] = []
    if not isinstance(events, list):
        return compact

    for event in events:
        if not isinstance(event, dict):
            continue
        row = [event.get("type"), event.get("label"), event.get("note")]
        optional_values = [
            event.get("event_date"),
            event.get("source"),
            event.get("source_url"),
            event.get("event_id"),
        ]
        if any(value not in (None, "") for value in optional_values):
            row.extend(optional_values)
            while len(row) > 3 and row[-1] in (None, ""):
                row.pop()
        compact.append(row)
    return compact


def infer_manifest_player_type(seasons: list[dict[str, object]]) -> str:
    roles = [season.get("player_type") for season in seasons if isinstance(season, dict)]
    if "two_way" in roles:
        return "two_way"
    if "hitter" in roles and "pitcher" in roles:
        return "two_way"
    if "pitcher" in roles:
        return "pitcher"
    return "hitter"


def player_history_id(player: dict[str, object]) -> str:
    fangraphs_id = player.get("fangraphs_id")
    if fangraphs_id is not None:
        return f"fg-{fangraphs_id}"
    player_key = player.get("player_key") or slugify(str(player.get("name") or "player"))
    return f"pk-{player_key}"


def slugify(value: str) -> str:
    return "-".join(value.lower().split())


def _normalize_row(row: dict[str, object]) -> dict[str, object]:
    """Rewrite alias column names to their canonical key so _pick is a direct lookup."""
    for canonical, aliases in STAT_ALIASES.items():
        if canonical in row:
            continue
        for alias in aliases:
            if alias in row:
                row[canonical] = row[alias]
                break
    return row


def _pick(row: dict[str, object] | None, field: str) -> object:
    if row is None:
        return None
    for alias in STAT_ALIASES[field]:
        if alias in row:
            return row[alias]
    return None


def _pick_optional(row: dict[str, object] | None, aliases: list[str]) -> object:
    if row is None:
        return None
    for alias in aliases:
        if alias in row:
            return row[alias]
    return None


def _coerce_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _coerce_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sum_nullable(*values: float | None) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)


def _season_sort_key(season: object) -> tuple[int, str]:
    if not isinstance(season, dict):
        return (0, "")
    year = _coerce_int(season.get("year")) or 0
    team = str(season.get("team") or "")
    return (year, team)
