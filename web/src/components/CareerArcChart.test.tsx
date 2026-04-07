import {fireEvent, render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import {CareerArcChart} from "./CareerArcChart";
import type {MetricDefinition, PlayerRecord} from "../types";

const WAR_METRIC: MetricDefinition = {
  key: "war",
  label: "WAR",
  format: "decimal"
};

function showTooltip(players: PlayerRecord[]) {
  const view = render(<CareerArcChart players={players} metric={WAR_METRIC} width={640} height={320} />);
  const point = view.container.querySelector("circle");
  if (!point) {
    throw new Error("Expected at least one chart point.");
  }
  fireEvent.mouseEnter(point, {clientX: 100, clientY: 100});
}

describe("CareerArcChart", () => {
  it("pairs injury and activation events in tooltip context", async () => {
    showTooltip([
      {
        name: "Mike Trout",
        seasons: [
          {
            year: 2023,
            player_type: "hitter",
            team: "LAA",
            stats: {war: 3.0},
            events: [
              {
                type: "injury",
                label: "10-day IL",
                note: "Placed on IL with hamstring strain.",
                event_date: "2023-05-03"
              },
              {
                type: "activation",
                label: "Activated from IL",
                note: "Returned to active roster.",
                event_date: "2023-05-18"
              }
            ],
            summary: "Missed time, then returned."
          }
        ]
      }
    ]);

    expect(
      await screen.findByText(
        "2023-05-03: 10-day IL: Placed on IL with hamstring strain. -> 2023-05-18: Activated from IL: Returned to active roster."
      )
    ).toBeInTheDocument();
  });

  it("shows unpaired injury events gracefully", async () => {
    showTooltip([
      {
        name: "Clayton Kershaw",
        seasons: [
          {
            year: 2023,
            player_type: "pitcher",
            team: "LAD",
            stats: {war: 2.3},
            events: [
              {
                type: "injury",
                label: "15-day IL",
                note: "Shoulder inflammation.",
                event_date: "2023-07-12"
              }
            ],
            summary: "Missed time with shoulder issue."
          }
        ]
      }
    ]);

    expect(await screen.findByText("2023-07-12: 15-day IL: Shoulder inflammation.")).toBeInTheDocument();
  });

  it("highlights the hovered legend player's chart data", () => {
    const view = render(
      <CareerArcChart
        players={[
          {
            name: "Mike Trout",
            seasons: [
              {
                year: 2023,
                player_type: "hitter",
                team: "LAA",
                stats: {war: 3.0},
                events: [],
                summary: ""
              }
            ]
          },
          {
            name: "Mookie Betts",
            seasons: [
              {
                year: 2023,
                player_type: "hitter",
                team: "LAD",
                stats: {war: 6.2},
                events: [],
                summary: ""
              }
            ]
          }
        ]}
        metric={WAR_METRIC}
        width={640}
        height={320}
      />
    );

    const troutLine = view.container.querySelector('path[data-player-name="Mike Trout"]');
    const bettsLine = view.container.querySelector('path[data-player-name="Mookie Betts"]');
    const bettsPoint = view.container.querySelector('circle[data-player-name="Mookie Betts"]');
    expect(troutLine).toHaveClass("chart-line-highlighted");
    expect(bettsLine).toHaveClass("chart-line-highlighted");
    expect(bettsPoint).toHaveClass("chart-point-highlighted");

    const troutLegend = screen.getByRole("button", {name: "Highlight Mike Trout"});
    fireEvent.mouseEnter(troutLegend);

    expect(troutLine).toHaveClass("chart-line-highlighted");
    expect(bettsLine).toHaveClass("chart-line-dimmed");
    expect(bettsPoint).toHaveClass("chart-point-dimmed");

    fireEvent.mouseLeave(troutLegend);

    expect(bettsLine).toHaveClass("chart-line-highlighted");
    expect(bettsPoint).toHaveClass("chart-point-highlighted");
  });
});
