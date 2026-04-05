from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AnnotationEvent:
    player_name: str
    year: int
    event_type: str
    label: str
    note: str

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.event_type,
            "label": self.label,
            "note": self.note,
        }


def load_annotation_index(path: str | Path | None) -> dict[tuple[str, int], list[AnnotationEvent]]:
    if path is None:
        return {}

    annotation_path = Path(path)
    if not annotation_path.exists():
        return {}

    index: dict[tuple[str, int], list[AnnotationEvent]] = {}
    with annotation_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            player_name = (row.get("player_name") or "").strip()
            year_value = (row.get("year") or "").strip()
            event_type = (row.get("event_type") or "note").strip()
            label = (row.get("label") or "").strip()
            note = (row.get("note") or "").strip()

            if not player_name or not year_value or not label:
                continue

            year = int(year_value)
            key = (player_name.lower(), year)
            index.setdefault(key, []).append(
                AnnotationEvent(
                    player_name=player_name,
                    year=year,
                    event_type=event_type,
                    label=label,
                    note=note,
                )
            )
    return index


def infer_team_change_events(seasons: list[dict[str, object]]) -> list[dict[str, object]]:
    inferred: list[dict[str, object]] = []
    previous_team: str | None = None

    for season in seasons:
        team = season.get("team")
        year = season.get("year")
        if not isinstance(team, str) or not isinstance(year, int):
            continue

        if previous_team and team and team != previous_team:
            inferred.append(
                {
                    "year": year,
                    "type": "team_change",
                    "label": f"Joined {team}",
                    "note": f"Changed teams after the previous season ({previous_team} -> {team}).",
                }
            )
        previous_team = team

    return inferred

