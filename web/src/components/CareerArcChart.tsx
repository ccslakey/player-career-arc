import {extent, format as d3Format, group, line, scaleLinear, scaleOrdinal} from "d3";
import {type MouseEvent, useMemo, useRef, useState} from "react";
import {formatMetric} from "../lib/format";
import type {EventAnnotation, MetricDefinition, PlayerRecord, TooltipDatum} from "../types";

const PALETTE = [
  "#005f73",
  "#9b2226",
  "#0a9396",
  "#ca6702",
  "#6a4c93",
  "#ae2012",
  "#3a86ff",
  "#8338ec",
  "#2a9d8f",
  "#264653"
];

export function CareerArcChart({
  players,
  metric,
  width = 980,
  height = 480
}: {
  players: PlayerRecord[];
  metric: MetricDefinition;
  width?: number;
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<{datum: TooltipDatum; x: number; y: number} | null>(null);

  const series = useMemo(() => flattenPlayers(players, metric), [players, metric]);

  const margins = {top: 18, right: 22, bottom: 42, left: 60};
  const innerWidth = width - margins.left - margins.right;
  const innerHeight = height - margins.top - margins.bottom;

  const years = expandExtent(extent(series, (datum: TooltipDatum) => datum.year));
  const values = expandExtent(extent(series, (datum: TooltipDatum) => datum.value));

  const x = scaleLinear().domain(years).nice().range([0, innerWidth]);
  const y = scaleLinear().domain(values).nice().range([innerHeight, 0]);
  const color = scaleOrdinal<string, string>().domain(players.map((player) => player.name)).range(PALETTE);

  const lineGenerator = line<TooltipDatum>()
    .defined((datum: TooltipDatum) => datum.value != null)
    .x((datum: TooltipDatum) => x(datum.year))
    .y((datum: TooltipDatum) => y(datum.value));

  const groupedSeries = Array.from(
    group(series, (datum: TooltipDatum) => datum.playerName).entries()
  ) as Array<[string, TooltipDatum[]]>;
  const xTicks: number[] = x.ticks(Math.min(8, Math.max(2, years[1] - years[0] + 1)));
  const yTicks: number[] = y.ticks(6);

  if (!series.length) {
    return (
      <div className="panel chart-panel">
        <p className="note">No season data is available for that metric yet.</p>
      </div>
    );
  }

  return (
    <div className="panel chart-panel" ref={containerRef}>
      <svg viewBox={`0 0 ${width} ${height}`} className="chart-svg" aria-label={`${metric.label} career arc chart`}>
        <g transform={`translate(${margins.left},${margins.top})`}>
          {yTicks.map((tick) => (
            <g key={`y-${tick}`} transform={`translate(0,${y(tick)})`}>
              <line className="chart-grid" x1={0} x2={innerWidth} />
              <text className="chart-axis-label chart-axis-label-y" x={-12} y={4}>
                {tick}
              </text>
            </g>
          ))}

          {xTicks.map((tick) => (
            <g key={`x-${tick}`} transform={`translate(${x(tick)},${innerHeight})`}>
              <line className="chart-axis-tick" y2={6} />
              <text className="chart-axis-label" y={22} textAnchor="middle">
                {d3Format("d")(tick)}
              </text>
            </g>
          ))}

          <line className="chart-axis" x1={0} x2={innerWidth} y1={innerHeight} y2={innerHeight} />
          <line className="chart-axis" y1={0} y2={innerHeight} />

          <text className="chart-axis-title" x={0} y={-2}>
            {metric.label}
          </text>

          {groupedSeries.map(([playerName, points]) => (
            <path
              key={playerName}
              className="chart-line"
              d={lineGenerator(points) ?? ""}
              stroke={color(playerName)}
            />
          ))}

          {series.map((datum) => (
            <circle
              key={`${datum.playerName}-${datum.year}`}
              className="chart-point"
              cx={x(datum.year)}
              cy={y(datum.value)}
              r={tooltip?.datum === datum ? 6.5 : 4.5}
              fill={color(datum.playerName)}
              onMouseEnter={(event) => updateTooltip(event, datum)}
              onMouseMove={(event) => updateTooltip(event, datum)}
              onMouseLeave={() => setTooltip(null)}
            />
          ))}
        </g>
      </svg>

      {tooltip && (
        <div className="chart-tooltip" style={{left: tooltip.x, top: tooltip.y}}>
          <div className="chart-tooltip-title">
            {tooltip.datum.playerName} · {tooltip.datum.year}
          </div>
          <div>
            {metric.label}: <strong>{formatMetric(metric, tooltip.datum.value)}</strong>
          </div>
          <div>Team: {tooltip.datum.team ?? "Unknown"}</div>
          <div>Role: {tooltip.datum.player_type ?? "Unknown"}</div>
          
          {tooltip.datum.events.length ? (
            <div className="chart-tooltip-events">
              <strong>Context</strong>
              {tooltip.datum.events.map((event, index) => (
                <div key={`${event.label ?? "event"}-${index}`}>
                  <div>{formatEventLine(event)}</div>
                  {event.source || event.confidence ? (
                    <div className="chart-tooltip-event-meta">
                      Source: {event.source ?? "unknown"} · Confidence: {event.confidence ?? "unknown"}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}

      <div className="chart-legend">
        {players.map((player) => (
          <span key={player.name} className="chart-legend-item">
            <span className="chart-legend-swatch" style={{background: color(player.name)}} />
            {player.name}
          </span>
        ))}
      </div>
    </div>
  );

  function updateTooltip(event: MouseEvent<SVGCircleElement>, datum: TooltipDatum) {
    const bounds = containerRef.current?.getBoundingClientRect();
    if (!bounds) {
      return;
    }

    setTooltip({
      datum,
      x: event.clientX - bounds.left + 14,
      y: event.clientY - bounds.top + 14
    });
  }
}

function flattenPlayers(players: PlayerRecord[], metric: MetricDefinition): TooltipDatum[] {
  return players.flatMap((player) =>
    player.seasons
      .filter((season) => season.stats?.[metric.key] != null)
      .map((season) => ({
        ...season,
        playerName: player.name,
        value: season.stats[metric.key] as number
      }))
  );
}

function expandExtent([min, max]: [number | undefined, number | undefined]): [number, number] {
  if (min == null || max == null) {
    return [0, 1];
  }

  if (min === max) {
    return [min - 1, max + 1];
  }

  return [min, max];
}

function formatEventLine(event: EventAnnotation): string {
  const eventLabel = event.label ?? event.type ?? "Event";
  if (event.note) {
    return `${eventLabel}: ${event.note}`;
  }
  return eventLabel;
}
