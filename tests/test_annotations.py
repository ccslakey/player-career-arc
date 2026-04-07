import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from career_arc.annotations import (
    fetch_bulk_transaction_injury_events,
    fetch_transaction_injury_events,
    load_annotation_index,
    merge_annotation_events,
)
from career_arc.pipeline import build_player_seasons_from_rows, compact_events
from career_arc.pipeline import apply_annotations_to_dataset


class AnnotationTests(unittest.TestCase):
    def test_transaction_events_map_to_injury_and_activation(self) -> None:
        payload = {
            "transactions": [
                {
                    "id": 1,
                    "date": "2023-05-03",
                    "typeDesc": "Injured List",
                    "description": "Placed on 10-day IL with hamstring strain.",
                },
                {
                    "id": 2,
                    "date": "2023-05-18",
                    "typeDesc": "Roster Move",
                    "description": "Activated from 10-day IL.",
                },
                {
                    "id": 3,
                    "date": "2023-06-01",
                    "typeDesc": "Trade",
                    "description": "Traded to LAD.",
                },
            ]
        }

        events = fetch_transaction_injury_events(
            mlbam_id=123,
            start_year=2023,
            end_year=2023,
            fetcher=lambda _url: payload,
        )

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["type"], "injury")
        self.assertEqual(events[0]["event_date"], "2023-05-03")
        self.assertEqual(events[1]["type"], "activation")
        self.assertEqual(events[1]["event_date"], "2023-05-18")
        self.assertTrue(all(event["source"] == "mlb_transactions" for event in events))

    def test_strict_il_filtering_excludes_non_il_medical_text(self) -> None:
        payload = {
            "transactions": [
                {
                    "id": 8,
                    "date": "2024-04-11",
                    "typeDesc": "Medical Update",
                    "description": "Soreness in shoulder.",
                }
            ]
        }
        events = fetch_transaction_injury_events(
            mlbam_id=123,
            start_year=2024,
            end_year=2024,
            fetcher=lambda _url: payload,
        )
        self.assertEqual(events, [])

    def test_bulk_transaction_fetch_returns_stats(self) -> None:
        payload_2023 = {
            "transactions": [
                {
                    "id": 1,
                    "date": "2023-05-03",
                    "typeDesc": "Injured List",
                    "description": "Placed on 10-day IL.",
                    "person": {"id": 123},
                },
                {
                    "id": 2,
                    "date": "2023-05-18",
                    "typeDesc": "Roster Move",
                    "description": "Activated from 10-day IL.",
                    "person": {"id": 123},
                },
                {
                    "id": 3,
                    "date": "2023-06-01",
                    "typeDesc": "Trade",
                    "description": "Traded to LAD.",
                    "person": {"id": 999},
                },
            ]
        }

        def fetcher(url: str) -> dict[str, object]:
            if "startDate=2023-01-01" in url:
                return payload_2023
            return {}

        events_by_player, stats = fetch_bulk_transaction_injury_events(
            mlbam_ids={123},
            start_year=2023,
            end_year=2024,
            fetcher=fetcher,
        )

        self.assertEqual(len(events_by_player.get(123, [])), 2)
        self.assertEqual(stats.years_requested, 2)
        self.assertEqual(stats.years_succeeded, 1)
        self.assertEqual(stats.years_failed, 1)
        self.assertEqual(stats.transactions_scanned, 3)
        self.assertEqual(stats.transactions_for_target_players, 2)
        self.assertEqual(stats.injury_events_emitted, 2)

    def test_load_annotation_index_supports_legacy_and_extended_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "annotations.csv"
            csv_path.write_text(
                "player_name,year,event_type,label,note\n"
                "Mike Trout,2021,injury,Calf strain,Missed time.\n"
                "Mookie Betts,2020,award,MVP runner-up,Finished second.\n",
                encoding="utf-8",
            )
            index = load_annotation_index(csv_path)
            self.assertEqual(len(index[("mike trout", 2021)]), 1)
            self.assertEqual(index[("mike trout", 2021)][0].source, "manual_csv")

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "annotations_extended.csv"
            csv_path.write_text(
                "player_name,year,event_date,event_type,label,note,source,source_url,event_id\n"
                "Mike Trout,2023,2023-05-03,injury,10-day IL,Placed on IL,manual_csv,https://example.com,mt-2023-il\n",
                encoding="utf-8",
            )
            index = load_annotation_index(csv_path)
            event = index[("mike trout", 2023)][0]
            self.assertEqual(event.event_date, "2023-05-03")
            self.assertEqual(event.source_url, "https://example.com")
            self.assertEqual(event.event_id, "mt-2023-il")

    def test_manual_override_replaces_transaction_event(self) -> None:
        merged = merge_annotation_events(
            player_id="fg-10155",
            year=2023,
            candidate_events=[
                {
                    "year": 2023,
                    "event_date": "2023-05-03",
                    "type": "injury",
                    "label": "10-day IL",
                    "note": "Placed on IL",
                    "source": "mlb_transactions",
                    "event_id": "tx-1",
                },
                {
                    "year": 2023,
                    "event_date": "2023-05-03",
                    "type": "injury",
                    "label": "10-day IL",
                    "note": "Manual override note",
                    "source": "manual_csv",
                    "event_id": "manual-1",
                },
            ],
        )
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["source"], "manual_csv")
        self.assertEqual(merged[0]["note"], "Manual override note")

    def test_missing_mlbam_id_still_keeps_manual_annotations(self) -> None:
        batting_rows = [
            {"Season": 2021, "IDfg": 10155, "Name": "Mike Trout", "Team": "LAA", "AB": 100, "AVG": 0.3, "WAR": 3.0}
        ]
        annotation_index = load_annotation_index(ROOT / "config" / "annotations.example.csv")
        seasons = build_player_seasons_from_rows(
            player_name="Mike Trout",
            batting_rows=batting_rows,
            pitching_rows=[],
            annotation_index=annotation_index,
            player_id="fg-10155",
            mlbam_id=None,
        )
        self.assertEqual(len(seasons), 1)
        labels = [event.get("label") for event in seasons[0]["events"]]
        # No network injuries without mlbam_id, but manual rows still flow by year.
        self.assertIn("Calf strain", labels)

    def test_compact_events_keeps_legacy_shape_and_extended_fields(self) -> None:
        compact = compact_events(
            [
                {"type": "note", "label": "Debut", "note": "First season"},
                {
                    "type": "injury",
                    "label": "10-day IL",
                    "note": "Placed on IL",
                    "event_date": "2023-05-03",
                    "source": "mlb_transactions",
                    "source_url": "https://statsapi.mlb.com/api/v1/transactions",
                    "event_id": "tx-1",
                },
            ]
        )

        self.assertEqual(compact[0], ["note", "Debut", "First season"])
        self.assertEqual(
            compact[1],
            [
                "injury",
                "10-day IL",
                "Placed on IL",
                "2023-05-03",
                "mlb_transactions",
                "https://statsapi.mlb.com/api/v1/transactions",
                "tx-1",
            ],
        )

    def test_apply_annotations_to_dataset_uses_existing_snapshot(self) -> None:
        dataset = {
            "metadata": {"metrics": [{"key": "war", "label": "WAR", "format": "decimal"}]},
            "players": [
                {
                    "player_key": "mike-trout",
                    "name": "Mike Trout",
                    "fangraphs_id": 10155,
                    "mlbam_id": None,
                    "seasons": [
                        {
                            "year": 2021,
                            "player_type": "hitter",
                            "team": "LAA",
                            "stats": {"war": 6.0},
                            "events": [],
                            "summary": "",
                        }
                    ],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.json"
            processed_output = Path(temp_dir) / "processed.json"
            frontend_output = Path(temp_dir) / "frontend.json"
            source_path.write_text(json.dumps(dataset), encoding="utf-8")

            refreshed = apply_annotations_to_dataset(
                dataset_input=source_path,
                annotations_csv=ROOT / "config" / "annotations.example.csv",
                processed_output=processed_output,
                frontend_output=frontend_output,
            )

            self.assertEqual(len(refreshed["players"]), 1)
            season = refreshed["players"][0]["seasons"][0]
            labels = [event.get("label") for event in season["events"]]
            self.assertIn("Calf strain", labels)
            self.assertTrue(processed_output.exists())
            self.assertTrue(frontend_output.exists())


if __name__ == "__main__":
    unittest.main()
