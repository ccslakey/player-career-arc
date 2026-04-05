from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlayerRequest:
    player_name: str
    fangraphs_id: int | None = None
    mlbam_id: int | None = None
    start_year: int | None = None
    end_year: int | None = None


@dataclass(frozen=True)
class ResolvedPlayer:
    player_name: str
    fangraphs_id: int | None
    mlbam_id: int | None
    start_year: int | None
    end_year: int | None


def parse_player_name(full_name: str) -> tuple[str, str]:
    parts = [part for part in full_name.strip().split() if part]
    if len(parts) < 2:
        raise ValueError(f"Expected a first and last name, received: {full_name!r}")
    return parts[0], parts[-1]


def resolve_player(request: PlayerRequest) -> ResolvedPlayer:
    if request.fangraphs_id is not None:
        return ResolvedPlayer(
            player_name=request.player_name,
            fangraphs_id=request.fangraphs_id,
            mlbam_id=request.mlbam_id,
            start_year=request.start_year,
            end_year=request.end_year,
        )

    try:
        from pybaseball import playerid_lookup
    except ImportError as exc:  # pragma: no cover - exercised only with live deps installed
        raise RuntimeError(
            "pybaseball is required for automatic player lookup. Install dependencies first."
        ) from exc

    first_name, last_name = parse_player_name(request.player_name)
    candidates = playerid_lookup(last_name, first_name)
    if candidates.empty:
        raise ValueError(f"No player lookup results found for {request.player_name!r}.")

    if "key_fangraphs" in candidates.columns:
        candidates = candidates[candidates["key_fangraphs"].notna()]
    if candidates.empty:
        raise ValueError(f"Lookup results for {request.player_name!r} did not include a Fangraphs id.")

    if request.mlbam_id is not None and "key_mlbam" in candidates.columns:
        explicit = candidates[candidates["key_mlbam"] == request.mlbam_id]
        if not explicit.empty:
            row = explicit.sort_values("mlb_played_last", ascending=False).iloc[0]
            return ResolvedPlayer(
                player_name=request.player_name,
                fangraphs_id=int(row["key_fangraphs"]),
                mlbam_id=int(row["key_mlbam"]) if row.get("key_mlbam") else request.mlbam_id,
                start_year=request.start_year,
                end_year=request.end_year,
            )

    sort_columns = [column for column in ("mlb_played_last", "mlb_played_first") if column in candidates.columns]
    if sort_columns:
        candidates = candidates.sort_values(sort_columns, ascending=False)
    row = candidates.iloc[0]

    mlbam_id = row.get("key_mlbam")
    return ResolvedPlayer(
        player_name=request.player_name,
        fangraphs_id=int(row["key_fangraphs"]),
        mlbam_id=int(mlbam_id) if mlbam_id == mlbam_id else None,
        start_year=request.start_year,
        end_year=request.end_year,
    )
