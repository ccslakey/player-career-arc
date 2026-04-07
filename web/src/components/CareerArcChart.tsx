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
          {(() => {
            const contextLines = buildTooltipContextLines(tooltip.datum.events);
            return (
              <>
          <div className="chart-tooltip-title">
            {tooltip.datum.playerName} · {tooltip.datum.year}
          </div>
          <div>
            {metric.label}: <strong>{formatMetric(metric, tooltip.datum.value)}</strong>
          </div>
          <div>Team: {tooltip.datum.team ?? "Unknown"}</div>
          <div>Role: {tooltip.datum.player_type ?? "Unknown"}</div>
          {tooltip.datum.summary ? <div className="chart-tooltip-summary">{tooltip.datum.summary}</div> : null}
          {contextLines.length ? (
            <div className="chart-tooltip-events">
              <strong>Context</strong>
              {contextLines.map((line, index) => (
                <div key={`${line}-${index}`}>
                  {line}
                </div>
              ))}
            </div>
          ) : null}
              </>
            );
          })()}
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

function buildTooltipContextLines(events: EventAnnotation[]): string[] {
  const sorted = [...(events ?? [])].sort(compareEventsByDate);
  const injuryQueue: EventAnnotation[] = [];
  const otherLines: string[] = [];

  for (const event of sorted) {
    if (event.type === "injury") {
      injuryQueue.push(event);
      continue;
    }

    if (event.type === "activation") {
      if (injuryQueue.length > 0) {
        const injury = injuryQueue.shift()!;
        otherLines.push(`${formatSingleEvent(injury)} -> ${formatSingleEvent(event)}`);
      } else {
        otherLines.push(formatSingleEvent(event));
      }
      continue;
    }

    otherLines.push(formatSingleEvent(event));
  }

  for (const unpairedInjury of injuryQueue) {
    otherLines.push(formatSingleEvent(unpairedInjury));
  }

  return otherLines;
}

function formatSingleEvent(event: EventAnnotation): string {
  const datePrefix = event.event_date ? `${event.event_date}: ` : "";
  const label = event.label ?? event.type ?? "Event";
  const note = event.note ? `: ${event.note}` : "";
  return `${datePrefix}${label}${note}`;
}

function compareEventsByDate(a: EventAnnotation, b: EventAnnotation): number {
  const leftDate = a.event_date ?? "9999-12-31";
  const rightDate = b.event_date ?? "9999-12-31";
  if (leftDate !== rightDate) {
    return leftDate.localeCompare(rightDate);
  }
  const leftTypeRank = eventTypeRank(a.type);
  const rightTypeRank = eventTypeRank(b.type);
  if (leftTypeRank !== rightTypeRank) {
    return leftTypeRank - rightTypeRank;
  }
  return (a.label ?? "").localeCompare(b.label ?? "");
}

function eventTypeRank(type: string | null | undefined): number {
  if (type === "injury") {
    return 0;
  }
  if (type === "activation") {
    return 1;
  }
  return 2;
}
