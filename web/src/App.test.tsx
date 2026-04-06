import {render, screen, waitFor} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";
import App from "./App";
import {jsonResponse, playerHistories, testManifest} from "./test/fixtures";

function installFetchMock() {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);

    if (url.endsWith("/data/players_manifest.json")) {
      return Promise.resolve(jsonResponse(testManifest));
    }

    const historyId = Object.keys(playerHistories).find((id) => url.endsWith(`/data/player-history/${id}.json`));
    if (historyId) {
      return Promise.resolve(jsonResponse(playerHistories[historyId]));
    }

    throw new Error(`Unexpected fetch: ${url}`);
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("App", () => {
  it("loads the default players and metric", async () => {
    const fetchMock = installFetchMock();
    window.history.replaceState({}, "", "/");

    render(<App />);

    expect(screen.getByText("Loading player manifest…")).toBeInTheDocument();

    await screen.findByRole("heading", {name: "Career arcs, season by season."});

    expect(screen.getByRole("button", {name: "Remove Mike Trout (2011-2024)"})).toBeInTheDocument();
    expect(screen.getByRole("button", {name: "Remove Clayton Kershaw (2008-2025)"})).toBeInTheDocument();
    expect(screen.getByRole("button", {name: "Remove Mookie Betts (2014-2025)"})).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toHaveValue("war");

    await waitFor(() => {
      expect(screen.getByText("MVP-caliber season.")).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/data/players_manifest.json"), expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/data/player-history/fg-10155.json"), expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/data/player-history/fg-2036.json"), expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/data/player-history/fg-13611.json"), expect.any(Object));
  });

  it("restores selected players and metric from the URL", async () => {
    installFetchMock();
    window.history.replaceState({}, "", "/?players=fg-2036,fg-19755&metric=avg");

    render(<App />);

    await screen.findByRole("heading", {name: "Career arcs, season by season."});

    expect(screen.getByRole("combobox")).toHaveValue("avg");
    expect(screen.getByRole("button", {name: "Remove Clayton Kershaw (2008-2025)"})).toBeInTheDocument();
    expect(screen.getByRole("button", {name: "Remove Aaron Judge (2016-2025)"})).toBeInTheDocument();
    expect(screen.queryByRole("button", {name: "Remove Mike Trout (2011-2024)"})).not.toBeInTheDocument();
  });
});
