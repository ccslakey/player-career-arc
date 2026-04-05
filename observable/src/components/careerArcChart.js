import * as d3 from "npm:d3";

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

export function careerArcChart({players, metric, width = 980, height = 480}) {
  const series = flattenPlayers(players, metric);
  const container = document.createElement("div");
  container.className = "panel";
  container.style.position = "relative";

  if (!series.length) {
    container.innerHTML = "<p class='note'>No season data is available for that metric yet.</p>";
    return container;
  }

  const margin = {top: 18, right: 22, bottom: 42, left: 60};
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;

  const years = d3.extent(series, (d) => d.year);
  const values = d3.extent(series, (d) => d.value);
  const x = d3.scaleLinear().domain(years).nice().range([0, innerWidth]);
  const y = d3.scaleLinear().domain(values).nice().range([innerHeight, 0]);
  const color = d3
    .scaleOrdinal()
    .domain(players.map((player) => player.name))
    .range(PALETTE);

  const svg = d3
    .create("svg")
    .attr("viewBox", [0, 0, width, height])
    .style("width", "100%")
    .style("height", "auto");

  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  g.append("g")
    .attr("transform", `translate(0,${innerHeight})`)
    .call(d3.axisBottom(x).tickFormat(d3.format("d")))
    .call((axis) => axis.selectAll("line,path").attr("stroke", "rgba(24, 32, 40, 0.2)"));

  g.append("g")
    .call(d3.axisLeft(y))
    .call((axis) => axis.selectAll("line,path").attr("stroke", "rgba(24, 32, 40, 0.2)"))
    .call((axis) => axis.selectAll(".tick line").attr("x2", innerWidth).attr("stroke-opacity", 0.3));

  const line = d3
    .line()
    .defined((d) => d.value != null)
    .x((d) => x(d.year))
    .y((d) => y(d.value));

  const grouped = d3.group(series, (d) => d.playerName);

  for (const [playerName, valuesForPlayer] of grouped) {
    g.append("path")
      .datum(valuesForPlayer)
      .attr("fill", "none")
      .attr("stroke", color(playerName))
      .attr("stroke-width", 2.6)
      .attr("d", line);
  }

  const tooltip = document.createElement("div");
  tooltip.style.position = "absolute";
  tooltip.style.pointerEvents = "none";
  tooltip.style.visibility = "hidden";
  tooltip.style.maxWidth = "280px";
  tooltip.style.padding = "0.75rem 0.85rem";
  tooltip.style.borderRadius = "12px";
  tooltip.style.background = "rgba(24, 32, 40, 0.94)";
  tooltip.style.color = "#fff";
  tooltip.style.boxShadow = "0 14px 40px rgba(24, 32, 40, 0.25)";
  tooltip.style.fontSize = "0.92rem";

  g.append("g")
    .selectAll("circle")
    .data(series)
    .join("circle")
    .attr("cx", (d) => x(d.year))
    .attr("cy", (d) => y(d.value))
    .attr("r", 4.5)
    .attr("fill", (d) => color(d.playerName))
    .attr("stroke", "#fff")
    .attr("stroke-width", 1.5)
    .on("mouseenter", function (event, d) {
      d3.select(this).attr("r", 6.5);
      tooltip.style.visibility = "visible";
      tooltip.innerHTML = renderTooltip(d, metric);
      moveTooltip(event);
    })
    .on("mousemove", function (event) {
      moveTooltip(event);
    })
    .on("mouseleave", function () {
      d3.select(this).attr("r", 4.5);
      tooltip.style.visibility = "hidden";
    });

  g.append("text")
    .attr("x", 0)
    .attr("y", -2)
    .attr("fill", "#59636d")
    .attr("font-size", 12)
    .text(metric.label);

  const legend = document.createElement("div");
  legend.style.display = "flex";
  legend.style.flexWrap = "wrap";
  legend.style.gap = "0.5rem 1rem";
  legend.style.marginTop = "0.85rem";
  legend.innerHTML = players
    .map(
      (player) =>
        `<span style="display:inline-flex;align-items:center;gap:0.45rem;"><span style="display:inline-block;width:12px;height:12px;border-radius:999px;background:${color(player.name)};"></span>${player.name}</span>`
    )
    .join("");

  container.append(svg.node(), tooltip, legend);
  return container;

  function moveTooltip(event) {
    const bounds = container.getBoundingClientRect();
    tooltip.style.left = `${event.clientX - bounds.left + 14}px`;
    tooltip.style.top = `${event.clientY - bounds.top + 14}px`;
  }
}

function flattenPlayers(players, metric) {
  return players.flatMap((player) =>
    player.seasons
      .filter((season) => season.stats?.[metric.key] != null)
      .map((season) => ({
        ...season,
        playerName: player.name,
        value: season.stats[metric.key]
      }))
  );
}

function renderTooltip(season, metric) {
  const events = Array.isArray(season.events) ? season.events : [];
  const summaryMarkup = season.summary
    ? `<div style="margin-top:0.45rem;">${season.summary}</div>`
    : "";
  const eventMarkup = events.length
    ? `<div style="margin-top:0.45rem;"><strong>Context</strong><br>${events
        .map((event) => `${event.label}${event.note ? `: ${event.note}` : ""}`)
        .join("<br>")}</div>`
    : "";

  return `
    <div style="font-weight:700;font-size:1rem;margin-bottom:0.2rem;">${season.playerName} · ${season.year}</div>
    <div>${metric.label}: <strong>${formatMetric(metric.key, season.value)}</strong></div>
    <div>Team: ${season.team}</div>
    <div>Role: ${season.player_type}</div>
    ${summaryMarkup}
    ${eventMarkup}
  `;
}

function formatMetric(metricKey, value) {
  if (["avg", "ops", "era", "whip", "war"].includes(metricKey)) {
    return d3.format(".3f")(value);
  }
  return d3.format("d")(value);
}
