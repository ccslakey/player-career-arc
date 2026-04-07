import {fireEvent, render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import {CareerArcChart} from "./CareerArcChart";
import type {MetricDefinition, PlayerRecord} from "../types";

const WAR_METRIC: MetricDefinition = {key: "war", label: "WAR", format: "decimal"};

function renderWithPlayers(players: PlayerRecord[]) {
  const result = render(<CareerArcChart players={players} metric={WAR_METRIC} width={640} height={320} />);
  const point = result.container.querySelector("circle");
  if (!point) {
    throw new Error("Expected at least one chart point");
  }
  fireEvent.mouseEnter(point, {clientX: 20, clientY: 20});
  return result;
}

describe("CareerArcChart", () => {
  it("shows source and confidence metadata in tooltip when present", async () => {
    renderWithPlayers([
      {
        name: "Event Tester",
        seasons: [
          {
            year: 2024,
            player_type: "hitter",
            team: "LAD",
            stats: {war: 5.4},
            events: [
              {
                label: "10-day IL",
                note: "Hamstring strain",
                source: "mlb_transactions",
                confidence: "high"
              }
            ],
            summary: "Recovered quickly."
          }
        ]
      }
    ]);

    expect(await screen.findByText("10-day IL: Hamstring strain")).toBeInTheDocument();
    expect(await screen.findByText("Source: mlb_transactions · Confidence: high")).toBeInTheDocument();
  });

  it("degrades gracefully when source and confidence are missing", async () => {
    renderWithPlayers([
      {
        name: "Legacy Event Tester",
        seasons: [
          {
            year: 2022,
            player_type: "hitter",
            team: "BOS",
            stats: {war: 3.1},
            events: [{label: "Debut", note: "First season"}],
            summary: "Solid debut."
          }
        ]
      }
    ]);

    expect(await screen.findByText("Debut: First season")).toBeInTheDocument();
    expect(screen.queryByText(/Source:/)).not.toBeInTheDocument();
  });
});
