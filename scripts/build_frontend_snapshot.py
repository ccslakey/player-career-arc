from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from career_arc.pipeline import build_observable_snapshot, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a compact Observable dataset from a full snapshot.")
    parser.add_argument("--input", required=True, help="Full processed dataset JSON.")
    parser.add_argument("--output", required=True, help="Compact Observable dataset JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    snapshot = build_observable_snapshot(payload)
    write_json(args.output, snapshot)
    print(f"Wrote compact Observable snapshot to {args.output}.")


if __name__ == "__main__":
    main()
