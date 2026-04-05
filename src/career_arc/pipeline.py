from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .annotations import infer_team_change_events, load_annotation_index
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


def build_dataset(
    players_csv: str | Path | None,
    annotations_csv: str | Path | None,
    processed_output: str | Path,
    observable_output: str | Path,
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
    write_json(observable_output, build_observable_snapshot(dataset))
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


def load_pybaseball_tables(start_year: int = 1900, end_year: int = 2024) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
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
    batting_rows: list[dict[str, object]],
    pitching_rows: list[dict[str, object]],
    annotation_index: dict[tuple[str, int], list[object]],
    start_year: int,
    end_year: int,
) -> list[dict[str, object]]:
    batting = filter_player_rows(batting_rows, fangraphs_id, start_year, end_year, "batting")
    pitching = filter_player_rows(pitching_rows, fangraphs_id, start_year, end_year, "pitching")
    return build_player_seasons_from_rows(player_name, batting, pitching, annotation_index)


def build_player_seasons_from_rows(
    player_name: str,
    batting_rows: list[dict[str, object]],
    pitching_rows: list[dict[str, object]],
    annotation_index: dict[tuple[str, int], list[object]],
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
        key = (player_name.lower(), year)
        extra_events = [event.to_dict() for event in annotation_index.get(key, [])]
        season["events"] = extra_events
        season["summary"] = generate_fallback_summary(player_name, season)
        seasons.append(season)

    inferred_events = infer_team_change_events(seasons)
    event_index = {event["year"]: event for event in inferred_events}
    for season in seasons:
        inferred = event_index.get(season["year"])
        if inferred:
            season["events"].insert(0, {k: v for k, v in inferred.items() if k != "year"})
            season["summary"] = generate_fallback_summary(player_name, season)

    return seasons


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


def write_json(path: str | Path, payload: dict[str, object]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_observable_snapshot(dataset: dict[str, object]) -> dict[str, object]:
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


def compact_seasons(seasons: object, metric_order: list[str]) -> list[list[object]]:
    compact: list[list[object]] = []
    if not isinstance(seasons, list):
        return compact

    for season in seasons:
        if not isinstance(season, dict):
            continue
        stats = season.get("stats", {})
        events = season.get("events", [])
        compact.append(
            [
                season.get("year"),
                season.get("player_type"),
                season.get("team"),
                compact_stats(stats, metric_order),
                compact_events(events),
            ]
        )
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
        compact.append([event.get("type"), event.get("label"), event.get("note")])
    return compact


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
