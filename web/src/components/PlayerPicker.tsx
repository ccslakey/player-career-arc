import {useMemo, useState} from "react";
import type {PlayerOption} from "../types";

const DEFAULT_PLACEHOLDER = "Search for a player";

export function PlayerPicker({
  options,
  selectedIds,
  onChange,
  maxSelections = 10,
  placeholder = DEFAULT_PLACEHOLDER
}: {
  options: PlayerOption[];
  selectedIds: string[];
  onChange: (next: string[]) => void;
  maxSelections?: number;
  placeholder?: string;
}) {
  const [query, setQuery] = useState("");
  const optionMap = useMemo(() => new Map(options.map((option) => [option.value, option])), [options]);
  const selected = selectedIds.map((value) => optionMap.get(value)).filter(Boolean) as PlayerOption[];

  const matches = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    if (!normalizedQuery) {
      return [];
    }

    return options
      .filter((option) => !selectedIds.includes(option.value))
      .filter((option) => {
        const haystack = `${option.label} ${option.searchText}`.toLowerCase();
        return haystack.includes(normalizedQuery);
      })
      .slice(0, 50);
  }, [options, query, selectedIds]);

  return (
    <div className="player-picker">
      <input
        className="player-picker-search"
        type="search"
        value={query}
        placeholder={placeholder}
        onChange={(event) => setQuery(event.target.value)}
      />

      <div className="player-picker-status">{selectedIds.length} of {maxSelections} selected</div>

      <div className="player-picker-selected">
        {selected.map((option) => (
          <button
            key={option.value}
            className="player-chip"
            type="button"
            onClick={() => onChange(selectedIds.filter((value) => value !== option.value))}
            title={`Remove ${option.label}`}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className="player-picker-results">
        {!query.trim() && <div className="player-picker-hint">Type a name to search the full player list.</div>}

        {query.trim() && !matches.length && (
          <div className="player-picker-hint">No matching players.</div>
        )}

        {matches.map((option) => (
          <button
            key={option.value}
            className="player-result"
            type="button"
            disabled={selectedIds.length >= maxSelections}
            onClick={() => {
              if (selectedIds.length >= maxSelections) {
                return;
              }
              onChange([...selectedIds, option.value]);
              setQuery("");
            }}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
