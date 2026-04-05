import {useMemo} from "react";
import type {MetricDefinition, PlayerRecord} from "../types";
import {formatMetric} from "../lib/format";

export function SeasonTable({
  players,
  metric
}: {
  players: PlayerRecord[];
  metric: MetricDefinition;
}) {
  const rows = useMemo(
    () =>
      players.flatMap((player) =>
        player.seasons
          .filter((season) => season.stats?.[metric.key] != null)
          .map((season) => ({
            player: player.name,
            year: season.year,
            team: season.team,
            role: season.player_type,
            metric: season.stats[metric.key] as number,
            events: (season.events ?? [])
              .map((event) => event.label)
              .filter(Boolean)
              .join(", "),
            summary: season.summary ?? ""
          }))
      ),
    [players, metric]
  );

  return (
    <div className="panel stat-table">
      <table>
        <thead>
          <tr>
            <th>Player</th>
            <th>Year</th>
            <th>Team</th>
            <th>Role</th>
            <th>{metric.label}</th>
            <th>Events</th>
            <th>Summary</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.player}-${row.year}`}>
              <td>{row.player}</td>
              <td>{row.year}</td>
              <td>{row.team ?? "Unknown"}</td>
              <td>{row.role ?? "Unknown"}</td>
              <td>{formatMetric(metric, row.metric)}</td>
              <td>{row.events || "—"}</td>
              <td>{row.summary || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
