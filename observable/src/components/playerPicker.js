const DEFAULT_PLACEHOLDER = "Search for a player";

export function playerPicker({
  players,
  initialSelectedNames = [],
  maxSelections = 10,
  placeholder = DEFAULT_PLACEHOLDER
}) {
  const container = document.createElement("div");
  container.className = "player-picker";

  const selected = new Set(initialSelectedNames.filter((name) => players.includes(name)).slice(0, maxSelections));
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
    for (const name of selected) {
      selectedWrap.append(renderSelectedChip(name));
    }

    results.replaceChildren();
    const matches = players.filter((name) => {
      if (selected.has(name)) return false;
      if (!query) return false;
      return name.toLowerCase().includes(query);
    });

    if (!query) {
      results.append(renderHint("Type a name to search the full player list."));
      return;
    }

    if (!matches.length) {
      results.append(renderHint("No matching players."));
      return;
    }

    for (const name of matches.slice(0, 50)) {
      results.append(renderResult(name));
    }
  }

  function renderSelectedChip(name) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "player-chip";
    chip.textContent = name;
    chip.title = `Remove ${name}`;
    chip.addEventListener("click", () => {
      selected.delete(name);
      notify();
    });
    return chip;
  }

  function renderResult(name) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "player-result";
    button.textContent = name;
    button.disabled = selected.size >= maxSelections;
    button.addEventListener("click", () => {
      if (selected.size >= maxSelections) return;
      selected.add(name);
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
