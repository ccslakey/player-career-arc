from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from career_arc.annotations import infer_team_change_events
from career_arc.pipeline import build_observable_snapshot, row_has_batting_activity, row_has_pitching_activity
from career_arc.summaries import build_summary_prompt, generate_fallback_summary


class SummaryTests(unittest.TestCase):
    def test_infer_team_change_events_detects_new_team(self) -> None:
        seasons = [
            {"year": 2019, "team": "BOS"},
            {"year": 2020, "team": "LAD"},
        ]
        events = infer_team_change_events(seasons)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "team_change")
        self.assertEqual(events[0]["year"], 2020)

    def test_fallback_summary_mentions_event_labels(self) -> None:
        season = {
            "year": 2021,
            "team": "LAA",
            "player_type": "hitter",
            "stats": {"avg": 0.333, "ops": 1.044, "hr": 39, "rbi": 79, "war": 6.2},
            "events": [{"label": "Calf strain", "note": "Missed most of the season."}],
        }
        summary = generate_fallback_summary("Mike Trout", season)
        self.assertIn("Calf strain", summary)
        self.assertIn("OPS 1.044", summary)

    def test_summary_prompt_contains_context(self) -> None:
        season = {
            "year": 2018,
            "team": "BOS",
            "player_type": "hitter",
            "stats": {"avg": 0.346, "ops": 1.078, "hr": 32, "rbi": 80, "war": 10.4},
            "events": [{"label": "MVP season", "note": "Won the AL MVP award."}],
        }
        prompt = build_summary_prompt("Mookie Betts", season)
        self.assertIn("MVP season", prompt)
        self.assertIn("OPS: 1.078", prompt)

    def test_batting_activity_requires_an_at_bat(self) -> None:
        self.assertTrue(row_has_batting_activity({"AB": 1}))
        self.assertFalse(row_has_batting_activity({"AB": 0}))

    def test_pitching_activity_accepts_pitches_or_fallbacks(self) -> None:
        self.assertTrue(row_has_pitching_activity({"Pitches": 1}))
        self.assertTrue(row_has_pitching_activity({"BF": 1}))
        self.assertTrue(row_has_pitching_activity({"IP": 0.1}))
        self.assertFalse(row_has_pitching_activity({"Pitches": 0, "BF": 0, "IP": 0.0}))

    def test_observable_snapshot_compacts_player_shape(self) -> None:
        full_dataset = {
            "metadata": {"metrics": [{"key": "avg"}, {"key": "war"}]},
            "players": [
                {
                    "player_key": "test-player",
                    "name": "Test Player",
                    "fangraphs_id": 1,
                    "seasons": [
                        {
                            "year": 2020,
                            "player_type": "hitter",
                            "team": "LAD",
                            "stats": {"avg": 0.3, "war": 2.1},
                            "events": [{"type": "note", "label": "Debut", "note": "First season"}],
                            "summary": "unused in compact output",
                        }
                    ],
                }
            ],
        }
        compact = build_observable_snapshot(full_dataset)
        self.assertTrue(compact["metadata"]["compact"])
        self.assertEqual(compact["players"][0]["n"], "Test Player")
        self.assertEqual(compact["players"][0]["s"][0][0], 2020)


if __name__ == "__main__":
    unittest.main()
