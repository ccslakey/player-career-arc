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
});
