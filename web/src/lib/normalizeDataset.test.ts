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

  it("supports legacy and enriched compact event tuples", () => {
    const dataset: CompactDatasetPayload = {
      metadata: {
        compact: true,
        metric_order: ["war"],
        metrics: [{key: "war", label: "WAR", format: "decimal"}]
      },
      players: [
        {
          k: "test-player",
          n: "Test Player",
          f: 123,
          s: [
            [
              2023,
              "hitter",
              "LAA",
              [3.0],
              [
                ["injury", "10-day IL", "Placed on IL"],
                [
                  "activation",
                  "Activated from IL",
                  "Returned to roster",
                  "2023-05-18",
                  "mlb_transactions",
                  "https://statsapi.mlb.com/api/v1/transactions",
                  "tx-2"
                ]
              ],
              "Recovered and returned."
            ]
          ]
        }
      ]
    };

    const normalized = normalizeDataset(dataset);
    const [legacy, enriched] = normalized.players[0].seasons[0].events;
    expect(legacy.label).toBe("10-day IL");
    expect(legacy.event_date).toBeNull();
    expect(enriched.type).toBe("activation");
    expect(enriched.event_date).toBe("2023-05-18");
    expect(enriched.source).toBe("mlb_transactions");
    expect(enriched.event_id).toBe("tx-2");
  });
});
