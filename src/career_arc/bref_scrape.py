"""Direct Baseball Reference scraping for pre-2008 season-level stats.

pybaseball's batting_stats_bref / pitching_stats_bref refuse years before 2008,
so this module fills the gap by scraping the league season pages directly:

    https://www.baseball-reference.com/leagues/majors/{YEAR}-standard-batting.shtml
    https://www.baseball-reference.com/leagues/majors/{YEAR}-standard-pitching.shtml

Pages are cached on disk (under pybaseball's cache directory) so a re-run does
not re-fetch. Live fetches honor the Crawl-delay: 3 directive in bref's
robots.txt and identify themselves with a project-specific User-Agent.

Output rows mirror the column names produced by batting_stats_bref /
pitching_stats_bref so downstream code in pipeline.py can consume them
without branching on data source.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Iterable

import requests

BREF_CRAWL_DELAY_SECONDS = 3
BREF_USER_AGENT = "career-arc-visualizer/0.1 (player-career-arc; respects Crawl-delay)"
BREF_BASE = "https://www.baseball-reference.com"

BATTING_TABLE_ID = "players_standard_batting"
PITCHING_TABLE_ID = "players_standard_pitching"

# bref data-stat attribute name -> column name expected by pipeline.py
BATTING_FIELD_MAP = {
    "name_display": "Name",
    "team_name_abbr": "Tm",
    "b_war": "WAR",
    "b_games": "G",
    "b_pa": "PA",
    "b_ab": "AB",
    "b_h": "H",
    "b_hr": "HR",
    "b_rbi": "RBI",
    "b_so": "SO",
    "b_bb": "BB",
    "b_batting_avg": "BA",
    "b_onbase_perc": "OBP",
    "b_slugging_perc": "SLG",
    "b_onbase_plus_slugging": "OPS",
}

PITCHING_FIELD_MAP = {
    "name_display": "Name",
    "team_name_abbr": "Tm",
    "p_war": "WAR",
    "p_w": "W",
    "p_l": "L",
    "p_earned_run_avg": "ERA",
    "p_g": "G",
    "p_gs": "GS",
    "p_ip": "IP",
    "p_h": "H",
    "p_so": "SO",
    "p_bb": "BB",
    "p_hr": "HR",
    "p_whip": "WHIP",
    "p_bfp": "BF",
}

NUMERIC_FIELDS = {
    "WAR", "G", "PA", "AB", "H", "HR", "RBI", "SO", "BB", "BA", "OBP", "SLG", "OPS",
    "W", "L", "ERA", "GS", "IP", "WHIP", "BF",
}


def scrape_bref_season(year: int, stat_type: str, cache_dir: Path | str) -> list[dict[str, object]]:
    """Return a list of player-season dicts for the given year and stat_type ('batting'|'pitching').

    Output matches batting_stats_bref / pitching_stats_bref shape: includes
    Name, Tm, mlbID is left absent (caller must attach via Chadwick register lookup),
    Lev='Maj-XX' so existing major-league filters pass, Season set to year.
    """
    if stat_type == "batting":
        slug = "standard-batting"
        table_id = BATTING_TABLE_ID
        field_map = BATTING_FIELD_MAP
    elif stat_type == "pitching":
        slug = "standard-pitching"
        table_id = PITCHING_TABLE_ID
        field_map = PITCHING_FIELD_MAP
    else:
        raise ValueError(f"Unknown stat_type: {stat_type}")

    url = f"{BREF_BASE}/leagues/majors/{year}-{slug}.shtml"
    html = _fetch_with_cache(url, Path(cache_dir))
    rows = _parse_player_table(html, table_id, field_map)

    for row in rows:
        row["Season"] = year
        # Synthesize a Lev value so the "Maj"-prefix filter in pipeline.py admits these rows.
        row.setdefault("Lev", "Maj")

    return rows


def attach_mlb_ids(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Use pybaseball's reverse lookup (Chadwick register, disk-cached) to add an
    mlbID to each row. Rows without a resolvable mapping retain bref_id only and
    will be skipped by pipeline.py's int-key grouping logic."""
    if not rows:
        return rows

    bref_ids = sorted({str(r["bref_id"]) for r in rows if r.get("bref_id")})
    if not bref_ids:
        return rows

    from pybaseball import playerid_reverse_lookup

    lookup_df = playerid_reverse_lookup(bref_ids, key_type="bbref")
    bref_to_mlb: dict[str, int] = {}
    for record in lookup_df.to_dict(orient="records"):
        bref_id = record.get("key_bbref")
        mlb_id = record.get("key_mlbam")
        if not bref_id or mlb_id is None:
            continue
        try:
            bref_to_mlb[str(bref_id)] = int(mlb_id)
        except (TypeError, ValueError):
            continue

    for row in rows:
        bref_id = row.get("bref_id")
        if bref_id is None:
            continue
        mlb_id = bref_to_mlb.get(str(bref_id))
        if mlb_id is not None:
            row["mlbID"] = mlb_id

    return rows


def _fetch_with_cache(url: str, cache_dir: Path) -> str:
    """Disk-cached GET. Honors BREF_CRAWL_DELAY_SECONDS only on real fetches —
    cache hits return immediately. Failed fetches raise; do not cache failures."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", url)
    cache_path = cache_dir / f"{safe_name}.html"

    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    response = requests.get(
        url,
        headers={"User-Agent": BREF_USER_AGENT, "Accept": "text/html"},
        timeout=60,
    )
    response.raise_for_status()
    cache_path.write_text(response.text, encoding="utf-8")
    time.sleep(BREF_CRAWL_DELAY_SECONDS)
    return response.text


def _parse_player_table(html: str, table_id: str, field_map: dict[str, str]) -> list[dict[str, object]]:
    """Parse the player-rows tbody for the given table id. Skips header rows
    inside the body that bref intersperses every ~25 rows."""
    table_pattern = re.compile(
        rf'<table[^>]*\bid="{re.escape(table_id)}"(?P<body>.*?)</table>',
        re.DOTALL,
    )
    table_match = table_pattern.search(html)
    if not table_match:
        return []

    tbody_match = re.search(r"<tbody>(.*?)</tbody>", table_match.group("body"), re.DOTALL)
    if not tbody_match:
        return []

    rows: list[dict[str, object]] = []
    for tr_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", tbody_match.group(1), re.DOTALL):
        tr_html = tr_match.group(1)
        # Skip header rows interspersed within tbody
        if 'class="thead"' in tr_html or "data-stat=\"header_" in tr_html:
            continue

        row = _parse_single_row(tr_html, field_map)
        if row is not None:
            rows.append(row)

    return rows


def _parse_single_row(tr_html: str, field_map: dict[str, str]) -> dict[str, object] | None:
    bref_id_match = re.search(r'data-append-csv="([a-z0-9.]+)"', tr_html)
    if not bref_id_match:
        return None

    row: dict[str, object] = {"bref_id": bref_id_match.group(1)}
    cell_pattern = re.compile(
        r'data-stat="([^"]+)"[^>]*>(?:<a[^>]*>)?([^<]*)',
    )
    for stat_name, raw_value in cell_pattern.findall(tr_html):
        column = field_map.get(stat_name)
        if column is None:
            continue
        value = raw_value.strip()
        if column in NUMERIC_FIELDS:
            row[column] = _parse_numeric(value)
        else:
            row[column] = value or None

    return row


def _parse_numeric(value: str) -> float | int | None:
    if not value:
        return None
    cleaned = value.replace(",", "")
    try:
        if "." in cleaned:
            return float(cleaned)
        return int(cleaned)
    except ValueError:
        return None
