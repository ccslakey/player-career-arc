import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import {SeasonTable} from "./SeasonTable";
import type {MetricDefinition, PlayerRecord} from "../types";

const WAR_METRIC: MetricDefinition = {key: "war", label: "WAR", format: "decimal"};

describe("SeasonTable", () => {
  it("renders event source and confidence metadata when present", () => {
    const players: PlayerRecord[] = [
      {
        name: "Event Tester",
        seasons: [
          {
            year: 2024,
            player_type: "hitter",
            team: "LAD",
            stats: {war: 5.2},
            events: [
              {
                type: "injury",
                label: "10-day IL",
                note: "Hamstring strain",
                source: "mlb_transactions",
                confidence: "high"
              }
            ],
            summary: "Returned quickly."
          }
        ]
      }
    ];

    render(<SeasonTable players={players} metric={WAR_METRIC} />);

    expect(screen.getByText(/10-day IL: Hamstring strain \[mlb_transactions · high\]/)).toBeInTheDocument();
  });

  it("falls back gracefully when event metadata is absent", () => {
    const players: PlayerRecord[] = [
      {
        name: "Legacy Event Tester",
        seasons: [
          {
            year: 2019,
            player_type: "hitter",
            team: "BOS",
            stats: {war: 3.2},
            events: [{type: "note", label: "Debut", note: "First season"}],
            summary: "Promising start."
          }
        ]
      }
    ];

    render(<SeasonTable players={players} metric={WAR_METRIC} />);

    expect(screen.getByText("Debut: First season")).toBeInTheDocument();
  });
});
