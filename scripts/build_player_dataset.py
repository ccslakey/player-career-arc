from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from career_arc.pipeline import build_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the player career dataset.")
    parser.add_argument(
        "--all-players",
        action="store_true",
        help="Build the dataset for every player with at least one at-bat or pitch in the chosen range.",
    )
    parser.add_argument(
        "--players",
        default=str(ROOT / "config" / "players.example.csv"),
        help="CSV file listing the players to include.",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        help="Optional lower year bound. Recommended when using --all-players.",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        help="Optional upper year bound. Recommended when using --all-players.",
    )
    parser.add_argument(
        "--annotations",
        default=str(ROOT / "config" / "annotations.example.csv"),
        help="Optional CSV file with injuries, awards, and other tooltip events.",
    )
    parser.add_argument(
        "--processed-output",
        default=str(ROOT / "data" / "processed" / "players.json"),
        help="Output path for the processed JSON snapshot.",
    )
    parser.add_argument(
        "--observable-output",
        default=str(ROOT / "observable" / "src" / "data" / "players.json"),
        help="Output path for the Observable data file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = build_dataset(
        players_csv=None if args.all_players else args.players,
        annotations_csv=args.annotations,
        processed_output=args.processed_output,
        observable_output=args.observable_output,
        include_all_players=args.all_players,
        start_year=args.start_year,
        end_year=args.end_year,
    )
    print(
        f"Wrote {len(dataset['players'])} players to {args.processed_output} and {args.observable_output}."
    )


if __name__ == "__main__":
    main()
