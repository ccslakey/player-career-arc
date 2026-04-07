from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ALLOWED_SOURCES = {
    "manual_csv",
    "mlb_transactions",
    "mlb_awards",
    "derived_stats",
    "inferred_team_change",
}

SOURCE_PRECEDENCE = {
    "manual_csv": 0,
    "mlb_transactions": 1,
    "mlb_awards": 1,
    "derived_stats": 2,
    "inferred_team_change": 2,
}

SOURCE_DEFAULTS = {
    "manual_csv": {"confidence": "high", "event_origin": "manual"},
    "mlb_transactions": {"confidence": "high", "event_origin": "official"},
    "mlb_awards": {"confidence": "high", "event_origin": "official"},
    "derived_stats": {"confidence": "medium", "event_origin": "derived"},
    "inferred_team_change": {"confidence": "medium", "event_origin": "inferred"},
}

INJURY_KEYWORDS = (
    "injured list",
    "10-day il",
    "15-day il",
    "60-day il",
    "7-day il",
    "7-day injured list",
)

INJURY_HEURISTIC_KEYWORDS = (
    "injury",
    "rehab",
    "hamstring",
    "elbow",
    "shoulder",
    "oblique",
    "wrist",
    "back",
    "knee",
)

JsonFetcher = Callable[[str], dict[str, object]]


@dataclass(frozen=True)
class AnnotationEvent:
    player_name: str
    year: int
    event_type: str
    label: str
    note: str
    source: str = "manual_csv"
    confidence: str = "high"
    source_url: str | None = None
    event_id: str | None = None
    event_origin: str | None = "manual"

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "type": self.event_type,
            "label": self.label,
            "note": self.note,
            "source": self.source,
            "confidence": self.confidence,
            "event_origin": self.event_origin or SOURCE_DEFAULTS["manual_csv"]["event_origin"],
        }
        if self.source_url:
            payload["source_url"] = self.source_url
        if self.event_id:
            payload["event_id"] = self.event_id
        return payload


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

            source = normalize_source((row.get("source") or "").strip() or "manual_csv")
            defaults = SOURCE_DEFAULTS[source]
            confidence = normalize_confidence((row.get("confidence") or "").strip(), defaults["confidence"])
            source_url = (row.get("source_url") or "").strip() or None
            event_id = (row.get("event_id") or "").strip() or None
            event_origin = (row.get("event_origin") or "").strip() or defaults["event_origin"]

            if not player_name or not year_value or not label:
                continue

            year = _coerce_int(year_value)
            if year is None:
                continue

            key = (player_name.lower(), year)
            index.setdefault(key, []).append(
                AnnotationEvent(
                    player_name=player_name,
                    year=year,
                    event_type=event_type,
                    label=label,
                    note=note,
                    source=source,
                    confidence=confidence,
                    source_url=source_url,
                    event_id=event_id,
                    event_origin=event_origin,
                )
            )
    return index


def collect_external_annotation_events(
    mlbam_id: int | None,
    start_year: int,
    end_year: int,
    fetcher: JsonFetcher | None = None,
) -> list[dict[str, object]]:
    if mlbam_id is None:
        return []

    events: list[dict[str, object]] = []
    events.extend(fetch_mlb_transaction_events(mlbam_id, start_year, end_year, fetcher))
    events.extend(fetch_mlb_award_events(mlbam_id, start_year, end_year, fetcher))
    return events


def fetch_mlb_transaction_events(
    mlbam_id: int,
    start_year: int,
    end_year: int,
    fetcher: JsonFetcher | None = None,
) -> list[dict[str, object]]:
    url = (
        "https://statsapi.mlb.com/api/v1/transactions?"
        + urlencode(
            {
                "playerId": mlbam_id,
                "startDate": f"{start_year}-01-01",
                "endDate": f"{end_year}-12-31",
            }
        )
    )
    payload = _safe_fetch_json(url, fetcher)
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        return []

    events: list[dict[str, object]] = []
    for transaction in transactions:
        if not isinstance(transaction, dict):
            continue
        year = extract_event_year(transaction)
        if year is None or year < start_year or year > end_year:
            continue

        type_desc = first_text(transaction, "typeDesc", "typeCode", "type")
        description = first_text(transaction, "description", "details", "note")
        label = type_desc or "Transaction"
        note = description

        from_team = first_text(transaction, "fromTeamName") or nested_text(transaction, "fromTeam", "name")
        to_team = first_text(transaction, "toTeamName") or nested_text(transaction, "toTeam", "name")
        if from_team and to_team and from_team != to_team:
            movement = f"{from_team} -> {to_team}"
            note = f"{note} ({movement})" if note else movement

        normalized_text = f"{label} {note}".lower()
        event_type = "injury" if is_injury_event(normalized_text) else "transaction"
        confidence = "high"
        if event_type == "injury" and not has_explicit_il_marker(normalized_text):
            confidence = "low"

        events.append(
            {
                "year": year,
                "type": event_type,
                "label": label,
                "note": note,
                "source": "mlb_transactions",
                "confidence": confidence,
                "source_url": url,
                "event_id": first_text(transaction, "id", "transactionId"),
                "event_origin": "official",
            }
        )

    return events


def fetch_mlb_award_events(
    mlbam_id: int,
    start_year: int,
    end_year: int,
    fetcher: JsonFetcher | None = None,
) -> list[dict[str, object]]:
    url = f"https://statsapi.mlb.com/api/v1/people/{mlbam_id}/awards"
    payload = _safe_fetch_json(url, fetcher)

    awards = payload.get("awards")
    if not isinstance(awards, list):
        people = payload.get("people")
        if isinstance(people, list):
            for person in people:
                if isinstance(person, dict) and isinstance(person.get("awards"), list):
                    awards = person["awards"]
                    break
    if not isinstance(awards, list):
        return []

    events: list[dict[str, object]] = []
    for award in awards:
        if not isinstance(award, dict):
            continue

        year = _coerce_int(award.get("season")) or extract_event_year(award)
        if year is None or year < start_year or year > end_year:
            continue

        events.append(
            {
                "year": year,
                "type": "award",
                "label": first_text(award, "name", "award") or "Award",
                "note": first_text(award, "notes", "note"),
                "source": "mlb_awards",
                "confidence": "high",
                "source_url": url,
                "event_id": first_text(award, "id"),
                "event_origin": "official",
            }
        )

    return events


def derive_milestone_events(seasons: list[dict[str, object]]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for season in seasons:
        year = _coerce_int(season.get("year"))
        if year is None:
            continue

        player_type = str(season.get("player_type") or "")
        stats = season.get("stats")
        if not isinstance(stats, dict):
            continue

        war = _coerce_float(stats.get("war"))
        if war is not None and war >= 6:
            events.append(
                {
                    "year": year,
                    "type": "milestone",
                    "label": "6+ WAR season",
                    "note": f"WAR {war:.1f}",
                    "source": "derived_stats",
                    "confidence": "medium",
                    "event_id": f"milestone-{year}-war-6",
                    "event_origin": "derived",
                }
            )

        if player_type in {"hitter", "two_way"}:
            hr = _coerce_int(stats.get("hr"))
            if hr is not None and hr >= 40:
                events.append(
                    {
                        "year": year,
                        "type": "milestone",
                        "label": "40+ HR season",
                        "note": f"{hr} home runs",
                        "source": "derived_stats",
                        "confidence": "medium",
                        "event_id": f"milestone-{year}-hr-40",
                        "event_origin": "derived",
                    }
                )

            ops = _coerce_float(stats.get("ops"))
            if ops is not None and ops >= 0.9:
                events.append(
                    {
                        "year": year,
                        "type": "milestone",
                        "label": ".900+ OPS season",
                        "note": f"OPS {ops:.3f}",
                        "source": "derived_stats",
                        "confidence": "medium",
                        "event_id": f"milestone-{year}-ops-900",
                        "event_origin": "derived",
                    }
                )

        if player_type in {"pitcher", "two_way"}:
            era = _coerce_float(stats.get("era"))
            if era is not None and era <= 3:
                events.append(
                    {
                        "year": year,
                        "type": "milestone",
                        "label": "Sub-3.00 ERA season",
                        "note": f"ERA {era:.2f}",
                        "source": "derived_stats",
                        "confidence": "medium",
                        "event_id": f"milestone-{year}-era-300",
                        "event_origin": "derived",
                    }
                )

            strikeouts = _coerce_int(stats.get("strikeouts"))
            if strikeouts is not None and strikeouts >= 200:
                events.append(
                    {
                        "year": year,
                        "type": "milestone",
                        "label": "200+ strikeout season",
                        "note": f"{strikeouts} strikeouts",
                        "source": "derived_stats",
                        "confidence": "medium",
                        "event_id": f"milestone-{year}-k-200",
                        "event_origin": "derived",
                    }
                )

    return events


def merge_annotation_events(
    player_id: str,
    year: int,
    candidate_events: list[dict[str, object]],
) -> list[dict[str, object]]:
    merged: dict[tuple[str, int, str, str], dict[str, object]] = {}

    for candidate in candidate_events:
        canonical = canonicalize_event(candidate)
        if canonical is None:
            continue

        event_year = _coerce_int(candidate.get("year")) or year
        if event_year != year:
            continue

        event_type = str(canonical.get("type") or "note")
        normalized_label = normalize_label(str(canonical.get("label") or ""))
        dedupe_key = (player_id, year, event_type, normalized_label)
        existing = merged.get(dedupe_key)
        if existing is None or should_replace(existing, canonical):
            merged[dedupe_key] = canonical

    return sorted(merged.values(), key=event_sort_key)


def canonicalize_event(event: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(event, dict):
        return None

    label = str(event.get("label") or "").strip()
    if not label:
        return None

    source = normalize_source(str(event.get("source") or "").strip() or "derived_stats")
    defaults = SOURCE_DEFAULTS[source]
    confidence = normalize_confidence(str(event.get("confidence") or "").strip(), defaults["confidence"])
    note = str(event.get("note") or "").strip()
    event_type = str(event.get("type") or "note").strip() or "note"
    source_url = str(event.get("source_url") or "").strip() or None
    event_id = str(event.get("event_id") or "").strip() or None
    event_origin = str(event.get("event_origin") or "").strip() or defaults["event_origin"]

    canonical: dict[str, object] = {
        "type": event_type,
        "label": label,
        "note": note,
        "source": source,
        "confidence": confidence,
        "event_origin": event_origin,
    }
    if source_url:
        canonical["source_url"] = source_url
    if event_id:
        canonical["event_id"] = event_id
    return canonical


def should_replace(existing: dict[str, object], candidate: dict[str, object]) -> bool:
    existing_rank = source_rank(existing.get("source"))
    candidate_rank = source_rank(candidate.get("source"))
    if candidate_rank != existing_rank:
        return candidate_rank < existing_rank

    existing_score = event_richness(existing)
    candidate_score = event_richness(candidate)
    if candidate_score != existing_score:
        return candidate_score > existing_score

    return False


def event_richness(event: dict[str, object]) -> int:
    return (
        int(bool(event.get("note"))) * 3
        + int(bool(event.get("source_url"))) * 2
        + int(bool(event.get("event_id")))
    )


def event_sort_key(event: dict[str, object]) -> tuple[int, str, str]:
    return (
        source_rank(event.get("source")),
        str(event.get("type") or ""),
        normalize_label(str(event.get("label") or "")),
    )


def source_rank(source: object) -> int:
    return SOURCE_PRECEDENCE.get(str(source or ""), 99)


def normalize_source(source: str) -> str:
    normalized = source.strip() or "derived_stats"
    if normalized in ALLOWED_SOURCES:
        return normalized
    return "derived_stats"


def normalize_confidence(confidence: str, fallback: str) -> str:
    candidate = confidence.strip().lower()
    if candidate in {"high", "medium", "low"}:
        return candidate
    return fallback


def normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip().lower())


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
                    "source": "inferred_team_change",
                    "confidence": "medium",
                    "event_id": f"team-change-{year}-{normalize_label(team)}",
                    "event_origin": "inferred",
                }
            )
        previous_team = team

    return inferred


def is_injury_event(text: str) -> bool:
    normalized = text.lower()
    return any(keyword in normalized for keyword in INJURY_KEYWORDS) or any(
        keyword in normalized for keyword in INJURY_HEURISTIC_KEYWORDS
    )


def has_explicit_il_marker(text: str) -> bool:
    normalized = text.lower()
    return any(keyword in normalized for keyword in INJURY_KEYWORDS)


def extract_event_year(payload: dict[str, object]) -> int | None:
    for key in ("date", "effectiveDate", "transactionDate", "awardDate"):
        value = payload.get(key)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).year
            except ValueError:
                if len(value) >= 4 and value[:4].isdigit():
                    return int(value[:4])
    return _coerce_int(payload.get("season"))


def first_text(payload: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def nested_text(payload: dict[str, object], parent_key: str, child_key: str) -> str | None:
    parent = payload.get(parent_key)
    if isinstance(parent, dict):
        value = parent.get(child_key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return None


def _safe_fetch_json(url: str, fetcher: JsonFetcher | None) -> dict[str, object]:
    try:
        if fetcher is not None:
            payload = fetcher(url)
            return payload if isinstance(payload, dict) else {}
        return _fetch_json(url)
    except (URLError, OSError, TimeoutError, ValueError):
        return {}


def _fetch_json(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": "career-arc-visualizer/0.1"})
    with urlopen(request, timeout=10) as response:
        payload = json.load(response)
    return payload if isinstance(payload, dict) else {}


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
