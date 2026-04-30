from __future__ import annotations

import csv
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

import requests

MLB_TRANSACTIONS_ENDPOINT = "https://statsapi.mlb.com/api/v1/transactions"
DEFAULT_INJURY_START_YEAR = 2002
MLB_TRANSACTIONS_CONCURRENCY = 4

IL_PATTERN = re.compile(r"(?:injured list|(?:7|10|15|60)-day il)", re.IGNORECASE)
ACTIVATION_PATTERN = re.compile(r"\b(?:activated|reinstated|returned)\b", re.IGNORECASE)
WHITESPACE_PATTERN = re.compile(r"\s+")

SOURCE_PRECEDENCE = {
    "manual_csv": 0,
    "mlb_transactions": 1,
    "inferred_team_change": 2,
}

JsonFetcher = Callable[[str], dict[str, object]]
ProgressLogger = Callable[[str], None]


@dataclass(frozen=True)
class AnnotationEvent:
    player_name: str
    year: int
    event_type: str
    label: str
    note: str
    event_date: str | None = None
    source: str = "manual_csv"
    source_url: str | None = None
    event_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "type": self.event_type,
            "label": self.label,
            "note": self.note,
            "year": self.year,
            "source": self.source,
        }
        if self.event_date:
            payload["event_date"] = self.event_date
        if self.source_url:
            payload["source_url"] = self.source_url
        if self.event_id:
            payload["event_id"] = self.event_id
        return payload


@dataclass
class TransactionFetchStats:
    years_requested: int = 0
    years_succeeded: int = 0
    years_failed: int = 0
    transactions_scanned: int = 0
    transactions_for_target_players: int = 0
    injury_events_emitted: int = 0


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

            event_date = normalize_event_date((row.get("event_date") or "").strip())
            source = (row.get("source") or "").strip() or "manual_csv"
            source_url = (row.get("source_url") or "").strip() or None
            event_id = (row.get("event_id") or "").strip() or None

            if not player_name or not label:
                continue

            year = coerce_int(year_value)
            if year is None and event_date:
                year = coerce_int(event_date[:4])
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
                    event_date=event_date,
                    source=source,
                    source_url=source_url,
                    event_id=event_id,
                )
            )
    return index


def fetch_transaction_injury_events(
    mlbam_id: int | None,
    start_year: int,
    end_year: int,
    fetcher: JsonFetcher | None = None,
    injury_start_year: int = DEFAULT_INJURY_START_YEAR,
) -> list[dict[str, object]]:
    if mlbam_id is None:
        return []

    query_start_year = max(start_year, injury_start_year)
    if query_start_year > end_year:
        return []

    query_params = {
        "playerId": mlbam_id,
        "sportId": 1,
        "startDate": f"{query_start_year}-01-01",
        "endDate": f"{end_year}-12-31",
    }
    query = urlencode(query_params)
    source_url = f"{MLB_TRANSACTIONS_ENDPOINT}?{query}"
    payload = safe_fetch_json(source_url, fetcher)

    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        return []

    events: list[dict[str, object]] = []
    for transaction in transactions:
        event = transaction_to_injury_event(
            transaction=transaction,
            source_url=source_url,
            start_year=query_start_year,
            end_year=end_year,
        )
        if event is not None:
            events.append(event)

    return events


def fetch_bulk_transaction_injury_events(
    mlbam_ids: set[int],
    start_year: int,
    end_year: int,
    fetcher: JsonFetcher | None = None,
    injury_start_year: int = DEFAULT_INJURY_START_YEAR,
    progress_logger: ProgressLogger | None = None,
) -> tuple[dict[int, list[dict[str, object]]], TransactionFetchStats]:
    stats = TransactionFetchStats()
    if not mlbam_ids:
        return {}, stats

    query_start_year = max(start_year, injury_start_year)
    if query_start_year > end_year:
        return {}, stats

    by_player: dict[int, list[dict[str, object]]] = {}
    years = list(range(query_start_year, end_year + 1))
    total_years = len(years)
    stats.years_requested = total_years

    def fetch_year(year: int) -> tuple[int, str, dict[str, object]]:
        query_params = {
            "sportId": 1,
            "startDate": f"{year}-01-01",
            "endDate": f"{year}-12-31",
        }
        source_url = f"{MLB_TRANSACTIONS_ENDPOINT}?{urlencode(query_params)}"
        return year, source_url, safe_fetch_json(source_url, fetcher)

    with ThreadPoolExecutor(max_workers=MLB_TRANSACTIONS_CONCURRENCY) as executor:
        results = list(executor.map(fetch_year, years))

    # Process results in year order so logs and event ordering stay deterministic.
    for index, (year, source_url, payload) in enumerate(results, start=1):
        if progress_logger is not None:
            progress_logger(
                f"[annotations] MLB transactions {index}/{total_years}: processing {year}"
            )
        transactions = payload.get("transactions")
        if not isinstance(transactions, list):
            stats.years_failed += 1
            if progress_logger is not None:
                progress_logger(
                    f"[annotations] MLB transactions {year}: failed (missing or invalid payload)."
                )
            continue
        stats.years_succeeded += 1
        stats.transactions_scanned += len(transactions)

        for transaction in transactions:
            if not isinstance(transaction, dict):
                continue
            player_id = transaction_player_id(transaction)
            if player_id is None or player_id not in mlbam_ids:
                continue
            stats.transactions_for_target_players += 1

            event = transaction_to_injury_event(
                transaction=transaction,
                source_url=source_url,
                start_year=query_start_year,
                end_year=end_year,
            )
            if event is None:
                continue
            by_player.setdefault(player_id, []).append(event)
            stats.injury_events_emitted += 1

    return by_player, stats


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
                }
            )
        previous_team = team

    return inferred


def merge_annotation_events(
    player_id: str,
    year: int,
    candidate_events: list[dict[str, object]],
) -> list[dict[str, object]]:
    deduped: dict[tuple[str, str, str, str], dict[str, object]] = {}
    for candidate in candidate_events:
        canonical = canonicalize_event(candidate, year)
        if canonical is None:
            continue

        canonical_year = coerce_int(canonical.get("year"))
        if canonical_year != year:
            continue

        dedupe_date = canonical.get("event_date") or f"{year}-01-01"
        event_type = str(canonical.get("type") or "note")
        normalized_label = normalize_label(str(canonical.get("label") or ""))
        dedupe_key = (player_id, dedupe_date, event_type, normalized_label)
        existing = deduped.get(dedupe_key)
        if existing is None or should_replace(existing, canonical):
            deduped[dedupe_key] = canonical

    return sorted(deduped.values(), key=event_sort_key)


def canonicalize_event(event: dict[str, object] | None, fallback_year: int) -> dict[str, object] | None:
    if not isinstance(event, dict):
        return None

    label = str(event.get("label") or "").strip()
    if not label:
        return None

    event_date = normalize_event_date(str(event.get("event_date") or "").strip())
    year = coerce_int(event.get("year"))
    if year is None and event_date:
        year = coerce_int(event_date[:4])
    year = year or fallback_year

    source = str(event.get("source") or "manual_csv").strip() or "manual_csv"
    canonical: dict[str, object] = {
        "year": year,
        "type": str(event.get("type") or "note").strip() or "note",
        "label": label,
        "note": str(event.get("note") or "").strip(),
        "source": source,
    }
    if event_date:
        canonical["event_date"] = event_date
    source_url = str(event.get("source_url") or "").strip()
    if source_url:
        canonical["source_url"] = source_url
    event_id = str(event.get("event_id") or "").strip()
    if event_id:
        canonical["event_id"] = event_id
    return canonical


def should_replace(existing: dict[str, object], candidate: dict[str, object]) -> bool:
    existing_rank = source_rank(existing.get("source"))
    candidate_rank = source_rank(candidate.get("source"))
    if existing_rank != candidate_rank:
        return candidate_rank < existing_rank

    if bool(candidate.get("note")) != bool(existing.get("note")):
        return bool(candidate.get("note"))

    if bool(candidate.get("event_id")) != bool(existing.get("event_id")):
        return bool(candidate.get("event_id"))

    return False


def source_rank(source: object) -> int:
    return SOURCE_PRECEDENCE.get(str(source or "").strip(), 99)


def event_sort_key(event: dict[str, object]) -> tuple[str, int, str]:
    year = coerce_int(event.get("year")) or 0
    event_date = str(event.get("event_date") or f"{year}-12-31")
    event_type = str(event.get("type") or "")
    type_order = 0 if event_type == "injury" else 1 if event_type == "activation" else 2
    label = normalize_label(str(event.get("label") or ""))
    return (event_date, type_order, label)


def normalize_label(value: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", value.strip().lower())


def is_il_related(text: str) -> bool:
    return bool(IL_PATTERN.search(text or ""))


def is_activation_event(text: str) -> bool:
    return bool(IL_PATTERN.search(text or "") and ACTIVATION_PATTERN.search(text or ""))


def build_transaction_label(event_type: str, type_desc: str, description: str) -> str:
    if event_type == "activation":
        return "Activated from IL"
    if type_desc:
        return type_desc
    if description:
        return "Placed on IL"
    return "Injured list transaction"


def transaction_to_injury_event(
    transaction: object,
    source_url: str,
    start_year: int,
    end_year: int,
) -> dict[str, object] | None:
    if not isinstance(transaction, dict):
        return None

    event_date = extract_event_date(transaction)
    year = coerce_int(event_date[:4]) if event_date else coerce_int(transaction.get("season"))
    if year is None or year < start_year or year > end_year:
        return None

    type_desc = first_text(transaction, "typeDesc", "typeCode", "type") or ""
    description = first_text(transaction, "description", "details", "note") or ""
    combined_text = f"{type_desc} {description}"
    if not is_il_related(combined_text):
        return None

    event_type = "activation" if is_activation_event(combined_text) else "injury"
    label = build_transaction_label(event_type, type_desc, description)
    note = description or type_desc
    return {
        "year": year,
        "event_date": event_date,
        "type": event_type,
        "label": label,
        "note": note,
        "source": "mlb_transactions",
        "source_url": source_url,
        "event_id": first_text(transaction, "id", "transactionId"),
    }


def extract_event_date(payload: dict[str, object]) -> str | None:
    for key in ("date", "effectiveDate", "transactionDate"):
        value = payload.get(key)
        if isinstance(value, str):
            normalized = normalize_event_date(value.strip())
            if normalized:
                return normalized
    return None


def normalize_event_date(value: str) -> str | None:
    if not value:
        return None
    candidate = value[:10]
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
        return candidate
    except ValueError:
        return None


def first_text(payload: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def transaction_player_id(transaction: dict[str, object]) -> int | None:
    person = transaction.get("person")
    if isinstance(person, dict):
        player_id = coerce_int(person.get("id"))
        if player_id is not None:
            return player_id
    return coerce_int(transaction.get("playerId"))


def safe_fetch_json(url: str, fetcher: JsonFetcher | None = None) -> dict[str, object]:
    try:
        if fetcher is not None:
            payload = fetcher(url)
            return payload if isinstance(payload, dict) else {}
        return fetch_json(url)
    except (requests.RequestException, TimeoutError, ValueError):
        return {}


def fetch_json(url: str) -> dict[str, object]:
    response = requests.get(
        url,
        timeout=20,
        headers={"User-Agent": "career-arc-visualizer/0.1"},
    )
    if response.status_code >= 400:
        return {}
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def coerce_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
