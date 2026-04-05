from __future__ import annotations


METRIC_LABELS = {
    "avg": "AVG",
    "hr": "HR",
    "rbi": "RBI",
    "ops": "OPS",
    "war": "WAR",
    "era": "ERA",
    "strikeouts": "SO",
    "whip": "WHIP",
}


def build_summary_prompt(player_name: str, season: dict[str, object]) -> str:
    stats = season.get("stats", {})
    events = season.get("events", [])
    metric_parts = []
    if isinstance(stats, dict):
        for key, label in METRIC_LABELS.items():
            value = stats.get(key)
            if value is not None:
                metric_parts.append(f"{label}: {value}")
    event_parts = []
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict):
                label = event.get("label")
                note = event.get("note")
                if label:
                    event_parts.append(f"{label}: {note}" if note else str(label))

    prompt_lines = [
        f"Write a concise baseball season summary for {player_name}.",
        f"Season: {season.get('year')}",
        f"Team: {season.get('team')}",
        f"Role: {season.get('player_type')}",
        f"Stats: {', '.join(metric_parts) if metric_parts else 'No stats available.'}",
        f"Context: {' | '.join(event_parts) if event_parts else 'No extra context provided.'}",
        "Keep it factual, 2-3 sentences, and mention notable performance swings or missed time if relevant.",
    ]
    return "\n".join(prompt_lines)


def generate_fallback_summary(player_name: str, season: dict[str, object]) -> str:
    stats = season.get("stats", {})
    if not isinstance(stats, dict):
        stats = {}

    player_type = season.get("player_type") or "player"
    year = season.get("year")
    team = season.get("team") or "Unknown team"
    events = season.get("events", [])

    if player_type == "pitcher":
        stat_bits = [
            _format_metric("era", stats.get("era")),
            _format_metric("whip", stats.get("whip")),
            _format_metric("strikeouts", stats.get("strikeouts")),
            _format_metric("war", stats.get("war")),
        ]
    else:
        stat_bits = [
            _format_metric("avg", stats.get("avg")),
            _format_metric("ops", stats.get("ops")),
            _format_metric("hr", stats.get("hr")),
            _format_metric("rbi", stats.get("rbi")),
            _format_metric("war", stats.get("war")),
        ]

    visible_stats = [bit for bit in stat_bits if bit]
    summary = f"In {year}, {player_name} suited up for {team} as a {player_type}."
    if visible_stats:
        summary += f" Key numbers: {', '.join(visible_stats)}."

    if isinstance(events, list) and events:
        notable_labels = [event.get("label") for event in events if isinstance(event, dict) and event.get("label")]
        if notable_labels:
            summary += f" Notable context: {'; '.join(notable_labels)}."

    return summary


def _format_metric(metric_key: str, value: object) -> str:
    if value is None:
        return ""
    label = METRIC_LABELS[metric_key]
    if metric_key in {"avg", "ops", "era", "whip", "war"}:
        return f"{label} {float(value):.3f}"
    return f"{label} {int(value)}"

