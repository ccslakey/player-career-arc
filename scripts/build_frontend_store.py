from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from career_arc.pipeline import build_history_store


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a manifest plus lazy-loaded player histories for Observable.")
    parser.add_argument("--input", required=True, help="Full processed dataset JSON.")
    parser.add_argument("--manifest-output", required=True, help="Output path for the player manifest JSON.")
    parser.add_argument("--history-dir", required=True, help="Output directory for per-player history files.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    manifest = build_history_store(
        dataset=payload,
        manifest_output=args.manifest_output,
        history_dir=args.history_dir,
    )
    print(f"Wrote manifest with {len(manifest['players'])} players to {args.manifest_output}.")


if __name__ == "__main__":
    main()
