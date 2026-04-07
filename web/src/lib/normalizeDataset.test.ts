import {describe, expect, it} from "vitest";
import type {CompactDatasetPayload} from "../types";
import {normalizeDataset} from "./normalizeDataset";

describe("normalizeDataset", () => {
  it("expands compact player history payloads", () => {
    const dataset: CompactDatasetPayload = {
      metadata: {
        compact: true,
        metric_order: ["avg", "war"],
        metrics: [{key: "avg", label: "Batting Avg", format: "average"}]
      },
      players: [
        {
          k: "test-player",
          n: "Test Player",
          f: 123,
          s: [[2020, "hitter", "LAD", [0.321, 5.4], [["note", "Debut", "First season"]], "Great year"]]
        }
      ]
    };

    const normalized = normalizeDataset(dataset);

    expect(normalized.players[0].name).toBe("Test Player");
    expect(normalized.players[0].seasons[0].stats.avg).toBe(0.321);
    expect(normalized.players[0].seasons[0].events[0].label).toBe("Debut");
    expect(normalized.players[0].seasons[0].summary).toBe("Great year");
  });

  it("supports legacy and enriched compact event rows", () => {
    const dataset: CompactDatasetPayload = {
      metadata: {
        compact: true,
        metric_order: ["war"],
        metrics: [{key: "war", label: "WAR", format: "decimal"}]
      },
      players: [
        {
          n: "Event Tester",
          s: [
            [
              2024,
              "hitter",
              "LAD",
              [5.2],
              [
                ["team_change", "Joined LAD", "Changed clubs"],
                [
                  "injury",
                  "10-day IL",
                  "Hamstring",
                  "mlb_transactions",
                  "high",
                  "https://example.com/tx",
                  "tx-123",
                  "official"
                ],
                {
                  type: "milestone",
                  label: "40+ HR season",
                  note: "42 home runs",
                  source: "derived_stats",
                  confidence: "medium"
                }
              ]
            ]
          ]
        }
      ]
    };

    const normalized = normalizeDataset(dataset);
    const [legacy, enriched, objectEvent] = normalized.players[0].seasons[0].events;

    expect(legacy.source).toBeNull();
    expect(enriched.source).toBe("mlb_transactions");
    expect(enriched.confidence).toBe("high");
    expect(enriched.source_url).toBe("https://example.com/tx");
    expect(enriched.event_id).toBe("tx-123");
    expect(objectEvent.source).toBe("derived_stats");
    expect(objectEvent.confidence).toBe("medium");
  });
});
