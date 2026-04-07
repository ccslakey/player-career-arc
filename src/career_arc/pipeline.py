from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from .annotations import (
    collect_external_annotation_events,
    derive_milestone_events,
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
    "name": ["Name", "name"],
    "fangraphs_id": ["IDfg", "key_fangraphs", "fangraphs_id"],
    "avg": ["AVG", "avg"],
    "hr": ["HR", "hr"],
    "rbi": ["RBI", "rbi"],
    "ops": ["OPS", "ops"],
    "war": ["WAR", "war"],
    "era": ["ERA", "era"],
    "strikeouts": ["SO", "K", "strikeouts"],
    "whip": ["WHIP", "whip"],
}

MLB_STATS_API_BASE = "https://statsapi.mlb.com/api/v1"


def build_dataset(
    players_csv: str | Path | None,
    annotations_csv: str | Path | None,
    processed_output: str | Path,
    frontend_output: str | Path,
    include_all_players: bool = False,
    start_year: int | None = None,
    end_year: int | None = None,
    source_preference: str = "mlb_statsapi",
) -> dict[str, object]:
    annotation_index = load_annotation_index(annotations_csv)

    if include_all_players:
        start_year = start_year or 2000
        end_year = end_year or datetime.now().year
        batting_rows, pitching_rows, id_system, resolved_source = load_stat_tables(
            start_year=start_year,
            end_year=end_year,
            source_preference=source_preference,
        )
        players = build_all_players_dataset(
            batting_rows=batting_rows,
            pitching_rows=pitching_rows,
            annotation_index=annotation_index,
            start_year=start_year,
            end_year=end_year,
            id_system=id_system,
        )
    else:
        if players_csv is None:
            raise ValueError("players_csv is required unless include_all_players=True.")

        player_requests = load_player_requests(players_csv)
        resolved_players = [resolve_player(request) for request in player_requests]
        start_year, end_year = determine_year_range(resolved_players)
        batting_rows, pitching_rows, id_system, resolved_source = load_stat_tables(
            start_year=start_year,
            end_year=end_year,
            source_preference=source_preference,
        )

        players = []
        for resolved in resolved_players:
            season_row_player_id = (
                resolved.fangraphs_id
                if id_system == "fangraphs"
                else resolved.mlbam_id
            )
            if season_row_player_id is None:
                raise ValueError(
                    f"Could not resolve a required player id for source {id_system!r} for {resolved.player_name!r}."
                )

            event_player_id = (
                f"fg-{resolved.fangraphs_id}"
                if resolved.fangraphs_id is not None
                else f"mlb-{resolved.mlbam_id}"
                if resolved.mlbam_id is not None
                else slugify(resolved.player_name)
            )

            seasons = build_player_seasons(
                resolved.player_name,
                season_row_player_id,
                event_player_id,
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
            "source": resolved_source,
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


def load_stat_tables(
    start_year: int,
    end_year: int,
    source_preference: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], str, str]:
    normalized = (source_preference or "").strip().lower() or "mlb_statsapi"
    if normalized not in {"mlb_statsapi", "auto", "fangraphs"}:
        raise ValueError(
            f"Invalid source_preference {source_preference!r}. "
            "Expected one of: mlb_statsapi, auto, fangraphs."
        )

    if normalized in {"mlb_statsapi", "auto"}:
        try:
            batting_rows, pitching_rows = load_mlb_statsapi_tables(start_year, end_year)
            return batting_rows, pitching_rows, "mlbam", "mlb_statsapi"
        except Exception as exc:
            if normalized == "mlb_statsapi":
                raise
            print(f"MLB Stats API load failed ({exc}); falling back to Fangraphs.")

    batting_rows, pitching_rows = load_pybaseball_tables(start_year, end_year)
    return batting_rows, pitching_rows, "fangraphs", "fangraphs_pybaseball"


def load_pybaseball_tables(start_year: int = 1900, end_year: int = datetime.now().year) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    from pybaseball import batting_stats, cache, pitching_stats

    cache.enable()
    batting_rows: list[dict[str, object]] = []
    pitching_rows: list[dict[str, object]] = []

    for year in range(start_year, end_year + 1):
        print(f"Loading Fangraphs batting data for {year}")
        batting_frame = batting_stats(year, year, qual=0)
        batting_rows.extend(batting_frame.to_dict(orient="records"))

        print(f"Loading Fangraphs pitching data for {year}")
        pitching_frame = pitching_stats(year, year, qual=0)
        pitching_rows.extend(pitching_frame.to_dict(orient="records"))

    return batting_rows, pitching_rows


def load_mlb_statsapi_tables(
    start_year: int = 1900,
    end_year: int = datetime.now().year,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    batting_rows: list[dict[str, object]] = []
    pitching_rows: list[dict[str, object]] = []

    for year in range(start_year, end_year + 1):
        print(f"Loading MLB Stats API batting data for {year}")
        team_map = load_mlb_team_abbreviations(year)
        batting_splits = fetch_mlb_stats_splits(year, "hitting")
        batting_rows.extend(convert_mlb_splits_to_rows(batting_splits, year, team_map, "hitting"))

        print(f"Loading MLB Stats API pitching data for {year}")
        pitching_splits = fetch_mlb_stats_splits(year, "pitching")
        pitching_rows.extend(convert_mlb_splits_to_rows(pitching_splits, year, team_map, "pitching"))

    return batting_rows, pitching_rows


def load_mlb_team_abbreviations(year: int) -> dict[int, str]:
    payload = fetch_json(
        f"{MLB_STATS_API_BASE}/teams",
        {"sportId": 1, "season": year},
    )
    teams = payload.get("teams")
    if not isinstance(teams, list):
        return {}

    team_map: dict[int, str] = {}
    for team in teams:
        if not isinstance(team, dict):
            continue
        team_id = _coerce_int(team.get("id"))
        abbreviation = str(team.get("abbreviation") or "").strip()
        if team_id is None or not abbreviation:
            continue
        team_map[team_id] = abbreviation
    return team_map


def fetch_mlb_stats_splits(year: int, group: str) -> list[dict[str, object]]:
    payload = fetch_json(
        f"{MLB_STATS_API_BASE}/stats",
        {
            "stats": "season",
            "group": group,
            "sportIds": 1,
            "season": year,
            "playerPool": "ALL",
            "limit": 10000,
        },
    )
    stats = payload.get("stats")
    if not isinstance(stats, list) or not stats:
        return []

    splits = stats[0].get("splits")
    return [split for split in splits if isinstance(split, dict)] if isinstance(splits, list) else []


def convert_mlb_splits_to_rows(
    splits: list[dict[str, object]],
    year: int,
    team_abbreviations: dict[int, str],
    group: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for split in splits:
        player = split.get("player")
        stat = split.get("stat")
        if not isinstance(player, dict) or not isinstance(stat, dict):
            continue

        player_id = _coerce_int(player.get("id"))
        player_name = str(player.get("fullName") or "").strip()
        if player_id is None or not player_name:
            continue

        team = split.get("team")
        team_id = _coerce_int(team.get("id")) if isinstance(team, dict) else None
        team_name = str(team.get("name") or "").strip() if isinstance(team, dict) else ""
        team_label = team_abbreviations.get(team_id) or team_name or "Unknown"

        row: dict[str, object] = {
            "Season": year,
            "IDfg": player_id,
            "Name": player_name,
            "Team": team_label,
        }

        if group == "hitting":
            row.update(
                {
                    "AB": _coerce_int(stat.get("atBats")),
                    "AVG": _coerce_float(stat.get("avg")),
                    "HR": _coerce_int(stat.get("homeRuns")),
                    "RBI": _coerce_int(stat.get("rbi")),
                    "OPS": _coerce_float(stat.get("ops")),
                    "SO": _coerce_int(stat.get("strikeOuts")),
                    "WAR": None,
                }
            )
        else:
            row.update(
                {
                    "Pitches": _coerce_int(stat.get("numberOfPitches")),
                    "BF": _coerce_int(stat.get("battersFaced")),
                    "IP": _coerce_float(stat.get("inningsPitched")),
                    "ERA": _coerce_float(stat.get("era")),
                    "WHIP": _coerce_float(stat.get("whip")),
                    "SO": _coerce_int(stat.get("strikeOuts")),
                    "WAR": None,
                }
            )

        rows.append(row)

    return rows


def build_all_players_dataset(
    batting_rows: list[dict[str, object]],
    pitching_rows: list[dict[str, object]],
    annotation_index: dict[tuple[str, int], list[object]],
    start_year: int,
    end_year: int,
    id_system: str,
) -> list[dict[str, object]]:
    grouped_players = group_rows_by_player(
        batting_rows=batting_rows,
        pitching_rows=pitching_rows,
        start_year=start_year,
        end_year=end_year,
    )
    players: list[dict[str, object]] = []

    for source_player_id, grouped in sorted(grouped_players.items(), key=lambda item: item[1]["name"]):
        event_player_id = (
            f"fg-{source_player_id}" if id_system == "fangraphs" else f"mlb-{source_player_id}"
        )
        seasons = build_player_seasons_from_rows(
            player_name=grouped["name"],
            batting_rows=grouped["batting"],
            pitching_rows=grouped["pitching"],
            annotation_index=annotation_index,
            player_id=event_player_id,
            mlbam_id=None,
        )
        if not seasons:
            continue

        players.append(
            {
                "player_key": slugify(grouped["name"]),
                "name": grouped["name"],
                "fangraphs_id": source_player_id if id_system == "fangraphs" else None,
                "mlbam_id": source_player_id if id_system == "mlbam" else None,
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
    season_row_player_id: int,
    event_player_id: str,
    mlbam_id: int | None,
    batting_rows: list[dict[str, object]],
    pitching_rows: list[dict[str, object]],
    annotation_index: dict[tuple[str, int], list[object]],
    start_year: int,
    end_year: int,
) -> list[dict[str, object]]:
    batting = filter_player_rows(batting_rows, season_row_player_id, start_year, end_year, "batting")
    pitching = filter_player_rows(pitching_rows, season_row_player_id, start_year, end_year, "pitching")
    return build_player_seasons_from_rows(
        player_name=player_name,
        batting_rows=batting,
        pitching_rows=pitching,
        annotation_index=annotation_index,
        player_id=event_player_id,
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

    first_year = min(season_years)
    last_year = max(season_years)
    inferred_events = infer_team_change_events(seasons)
    derived_events = derive_milestone_events(seasons)
    official_events = collect_external_annotation_events(mlbam_id, first_year, last_year)
    generated_by_year = index_events_by_year(official_events + inferred_events + derived_events)
    dedupe_player_id = player_id or slugify(player_name)

    for season in seasons:
        year = season["year"]
        candidates: list[dict[str, object]] = list(generated_by_year.get(year, []))
        key = (player_name.lower(), year)

        for manual_event in annotation_index.get(key, []):
            if hasattr(manual_event, "to_dict"):
                payload = manual_event.to_dict()
            elif isinstance(manual_event, dict):
                payload = manual_event
            else:
                continue
            if isinstance(payload, dict):
                candidates.append({"year": year, **payload})

        season["events"] = merge_annotation_events(
            player_id=dedupe_player_id,
            year=year,
            candidate_events=candidates,
        )
        season["summary"] = generate_fallback_summary(player_name, season)

    return seasons


def index_events_by_year(events: list[dict[str, object]]) -> dict[int, list[dict[str, object]]]:
    indexed: dict[int, list[dict[str, object]]] = {}
    for event in events:
        year = _coerce_int(event.get("year")) if isinstance(event, dict) else None
        if year is None:
            continue
        indexed.setdefault(year, []).append(event)
    return indexed


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
                    "f": player.get("fangraphs_id") or player.get("mlbam_id"),
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
                    "f": player.get("fangraphs_id") or player.get("mlbam_id"),
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
        "f": player.get("fangraphs_id") or player.get("mlbam_id"),
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
            event.get("source"),
            event.get("confidence"),
            event.get("source_url"),
            event.get("event_id"),
            event.get("event_origin"),
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
    mlbam_id = player.get("mlbam_id")
    if mlbam_id is not None:
        return f"mlb-{mlbam_id}"
    player_key = player.get("player_key") or slugify(str(player.get("name") or "player"))
    return f"pk-{player_key}"


def slugify(value: str) -> str:
    return "-".join(value.lower().split())


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


def fetch_json(url: str, query_params: dict[str, object]) -> dict[str, object]:
    params = {
        key: value
        for key, value in query_params.items()
        if value is not None and value != ""
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=20,
            headers={"User-Agent": "career-arc-visualizer/0.1"},
        )
        if response.status_code >= 400:
            return {}
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    except (requests.RequestException, ValueError):
        return {}
