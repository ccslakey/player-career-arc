import {useState} from "react";
import {render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {describe, expect, it, vi} from "vitest";
import {PlayerPicker} from "./PlayerPicker";
import type {PlayerOption} from "../types";

function makeOptions(count: number): PlayerOption[] {
  return Array.from({length: count}, (_, index) => ({
    value: `fg-${index + 1}`,
    label: `Player ${index + 1} (2000-2001)`,
    searchText: `player ${index + 1} fg-${index + 1}`
  }));
}

describe("PlayerPicker", () => {
  it("limits broad searches to 50 results", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(<PlayerPicker options={makeOptions(75)} selectedIds={[]} onChange={onChange} />);

    await user.type(screen.getByRole("searchbox"), "player");

    expect(screen.getAllByRole("button")).toHaveLength(50);
  });

  it("adds and removes players through the callback", async () => {
    const user = userEvent.setup();
    const options = [
      {value: "fg-1", label: "Mike Trout (2011-2024)", searchText: "Mike Trout 10155 hitter"},
      {value: "fg-2", label: "Clayton Kershaw (2008-2025)", searchText: "Clayton Kershaw 2036 pitcher"}
    ];

    function Wrapper() {
      const [selectedIds, setSelectedIds] = useState<string[]>(["fg-1"]);
      return <PlayerPicker options={options} selectedIds={selectedIds} onChange={setSelectedIds} />;
    }

    render(<Wrapper />);

    expect(screen.getByRole("button", {name: "Remove Mike Trout (2011-2024)"})).toBeInTheDocument();

    await user.click(screen.getByRole("button", {name: "Remove Mike Trout (2011-2024)"}));
    expect(screen.queryByRole("button", {name: "Mike Trout (2011-2024)"})).not.toBeInTheDocument();

    await user.type(screen.getByRole("searchbox"), "kershaw");
    await user.click(screen.getByRole("button", {name: "Clayton Kershaw (2008-2025)"}));

    expect(screen.getByRole("button", {name: "Remove Clayton Kershaw (2008-2025)"})).toBeInTheDocument();
  });
});
