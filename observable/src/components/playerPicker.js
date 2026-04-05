const DEFAULT_PLACEHOLDER = "Search for a player";

export function playerPicker({
  options,
  initialSelectedValues = [],
  maxSelections = 10,
  placeholder = DEFAULT_PLACEHOLDER
}) {
  const container = document.createElement("div");
  container.className = "player-picker";

  const optionMap = new Map(options.map((option) => [option.value, option]));
  const selected = new Set(
    initialSelectedValues.filter((value) => optionMap.has(value)).slice(0, maxSelections)
  );
  let query = "";

  const search = document.createElement("input");
  search.type = "search";
  search.className = "player-picker-search";
  search.placeholder = placeholder;

  const status = document.createElement("div");
  status.className = "player-picker-status";

  const selectedWrap = document.createElement("div");
  selectedWrap.className = "player-picker-selected";

  const results = document.createElement("div");
  results.className = "player-picker-results";

  search.addEventListener("input", () => {
    query = search.value.trim().toLowerCase();
    render();
  });

  Object.defineProperty(container, "value", {
    get() {
      return Array.from(selected);
    }
  });

  container.append(search, status, selectedWrap, results);
  render();
  return container;

  function render() {
    status.textContent = `${selected.size} of ${maxSelections} selected`;

    selectedWrap.replaceChildren();
    for (const value of selected) {
      selectedWrap.append(renderSelectedChip(optionMap.get(value)));
    }

    results.replaceChildren();
    const matches = options.filter((option) => {
      if (selected.has(option.value)) return false;
      if (!query) return false;
      const haystack = `${option.label} ${option.searchText ?? ""}`.toLowerCase();
      return haystack.includes(query);
    });

    if (!query) {
      results.append(renderHint("Type a name to search the full player list."));
      return;
    }

    if (!matches.length) {
      results.append(renderHint("No matching players."));
      return;
    }

    for (const option of matches.slice(0, 50)) {
      results.append(renderResult(option));
    }
  }

  function renderSelectedChip(option) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "player-chip";
    chip.textContent = option.label;
    chip.title = `Remove ${option.label}`;
    chip.addEventListener("click", () => {
      selected.delete(option.value);
      notify();
    });
    return chip;
  }

  function renderResult(option) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "player-result";
    button.textContent = option.label;
    button.disabled = selected.size >= maxSelections;
    button.addEventListener("click", () => {
      if (selected.size >= maxSelections) return;
      selected.add(option.value);
      search.value = "";
      query = "";
      notify();
    });
    return button;
  }

  function renderHint(text) {
    const hint = document.createElement("div");
    hint.className = "player-picker-hint";
    hint.textContent = text;
    return hint;
  }

  function notify() {
    render();
    container.dispatchEvent(new Event("input", {bubbles: true}));
  }
}
