from pathlib import Path
import csv
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from career_arc.annotations import (
    AnnotationEvent,
    canonicalize_event,
    fetch_mlb_transaction_events,
    load_annotation_index,
    merge_annotation_events,
)
from career_arc.pipeline import build_player_seasons_from_rows, compact_events


class AnnotationTests(unittest.TestCase):
    def test_load_annotation_index_supports_legacy_and_extended_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_path = Path(temp_dir) / "legacy.csv"
            legacy_path.write_text(
                "player_name,year,event_type,label,note\n"
                "Mike Trout,2021,injury,Calf strain,Missed time.\n",
                encoding="utf-8",
            )

            extended_path = Path(temp_dir) / "extended.csv"
            with extended_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "player_name",
                        "year",
                        "event_type",
                        "label",
                        "note",
                        "source",
                        "confidence",
                        "source_url",
                        "event_id",
                        "event_origin",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "player_name": "Mookie Betts",
                        "year": "2020",
                        "event_type": "award",
                        "label": "MVP runner-up",
                        "note": "Second in MVP vote.",
                    }
                )
                writer.writerow(
                    {
                        "player_name": "Mookie Betts",
                        "year": "2023",
                        "event_type": "transaction",
                        "label": "Extension signed",
                        "note": "Multi-year extension",
                        "source": "mlb_transactions",
                        "confidence": "high",
                        "source_url": "https://example.com/tx",
                        "event_id": "tx-123",
                        "event_origin": "official",
                    }
                )

            legacy_index = load_annotation_index(legacy_path)
            legacy_event = legacy_index[("mike trout", 2021)][0].to_dict()
            self.assertEqual(legacy_event["source"], "manual_csv")
            self.assertEqual(legacy_event["confidence"], "high")

            extended_index = load_annotation_index(extended_path)
            legacy_shaped_row = extended_index[("mookie betts", 2020)][0].to_dict()
            explicit_row = extended_index[("mookie betts", 2023)][0].to_dict()
            self.assertEqual(legacy_shaped_row["source"], "manual_csv")
            self.assertEqual(legacy_shaped_row["confidence"], "high")
            self.assertEqual(explicit_row["source"], "mlb_transactions")
            self.assertEqual(explicit_row["event_id"], "tx-123")

    def test_merge_annotation_events_applies_precedence_and_dedupes(self) -> None:
        merged = merge_annotation_events(
            player_id="fg-123",
            year=2023,
            candidate_events=[
                {
                    "year": 2023,
                    "type": "transaction",
                    "label": "Traded to LAD",
                    "note": "Official feed event",
                    "source": "mlb_transactions",
                    "confidence": "high",
                },
                {
                    "year": 2023,
                    "type": "transaction",
                    "label": "  traded   to lad  ",
                    "note": "Derived duplicate",
                    "source": "derived_stats",
                    "confidence": "medium",
                },
                {
                    "year": 2023,
                    "type": "transaction",
                    "label": "Traded to LAD",
                    "note": "Manual correction",
                    "source": "manual_csv",
                    "confidence": "high",
                },
                {
                    "year": 2023,
                    "type": "award",
                    "label": "Silver Slugger",
                    "note": "",
                    "source": "mlb_awards",
                    "confidence": "high",
                },
            ],
        )

        self.assertEqual(len(merged), 2)
        transaction = next(event for event in merged if event["type"] == "transaction")
        self.assertEqual(transaction["source"], "manual_csv")
        self.assertEqual(transaction["note"], "Manual correction")

    def test_confidence_defaults_and_transaction_injury_tiers(self) -> None:
        self.assertEqual(canonicalize_event({"label": "Manual note", "source": "manual_csv"})["confidence"], "high")
        self.assertEqual(canonicalize_event({"label": "Award", "source": "mlb_awards"})["confidence"], "high")
        self.assertEqual(canonicalize_event({"label": "Derived", "source": "derived_stats"})["confidence"], "medium")
        self.assertEqual(
            canonicalize_event({"label": "Team change", "source": "inferred_team_change"})["confidence"],
            "medium",
        )

        payload = {
            "transactions": [
                {
                    "id": "1",
                    "date": "2023-06-12",
                    "typeDesc": "Injured List",
                    "description": "Placed on 10-day IL with left hamstring strain",
                },
                {
                    "id": "2",
                    "date": "2023-07-20",
                    "typeDesc": "Medical Update",
                    "description": "Shoulder discomfort",
                },
                {
                    "id": "3",
                    "date": "2023-08-01",
                    "typeDesc": "Trade",
                    "description": "Traded to LAD",
                },
            ]
        }
        events = fetch_mlb_transaction_events(
            mlbam_id=123,
            start_year=2023,
            end_year=2023,
            fetcher=lambda _url: payload,
        )

        explicit_il = next(event for event in events if event["event_id"] == "1")
        heuristic_injury = next(event for event in events if event["event_id"] == "2")
        trade = next(event for event in events if event["event_id"] == "3")
        self.assertEqual(explicit_il["type"], "injury")
        self.assertEqual(explicit_il["confidence"], "high")
        self.assertEqual(heuristic_injury["type"], "injury")
        self.assertEqual(heuristic_injury["confidence"], "low")
        self.assertEqual(trade["type"], "transaction")

    def test_build_player_seasons_merges_annotations_and_keeps_summary(self) -> None:
        annotation_index = {
            ("test player", 2023): [
                AnnotationEvent(
                    player_name="Test Player",
                    year=2023,
                    event_type="note",
                    label="Manual note",
                    note="Added manually",
                    source="manual_csv",
                    confidence="high",
                )
            ]
        }
        batting_rows = [
            {"Season": 2022, "IDfg": 999, "Name": "Test Player", "Team": "BOS", "AB": 100, "AVG": 0.301, "WAR": 3.1},
            {"Season": 2023, "IDfg": 999, "Name": "Test Player", "Team": "LAD", "AB": 100, "AVG": 0.311, "WAR": 5.2},
        ]
        pitching_rows: list[dict[str, object]] = []

        seasons = build_player_seasons_from_rows(
            player_name="Test Player",
            batting_rows=batting_rows,
            pitching_rows=pitching_rows,
            annotation_index=annotation_index,
            player_id="fg-999",
            mlbam_id=None,
        )

        self.assertEqual(len(seasons), 2)
        season_2023 = next(season for season in seasons if season["year"] == 2023)
        labels = [event.get("label") for event in season_2023["events"]]
        self.assertIn("Manual note", labels)
        self.assertIn("Joined LAD", labels)
        self.assertIn("Test Player", season_2023["summary"])

    def test_compact_events_keeps_legacy_rows_and_supports_extended_metadata(self) -> None:
        compact = compact_events(
            [
                {"type": "note", "label": "Debut", "note": "First season"},
                {
                    "type": "injury",
                    "label": "10-day IL",
                    "note": "Hamstring",
                    "source": "mlb_transactions",
                    "confidence": "high",
                    "source_url": "https://example.com/tx",
                    "event_id": "tx-123",
                    "event_origin": "official",
                },
            ]
        )

        self.assertEqual(compact[0], ["note", "Debut", "First season"])
        self.assertEqual(compact[1][0:5], ["injury", "10-day IL", "Hamstring", "mlb_transactions", "high"])
        self.assertEqual(compact[1][-2:], ["tx-123", "official"])


if __name__ == "__main__":
    unittest.main()
