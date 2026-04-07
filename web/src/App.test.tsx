import {render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {describe, expect, it, vi} from "vitest";
import App from "./App";
import {jsonResponse, playerHistories, testManifest} from "./test/fixtures";

function installFetchMock({
  manifestPayload = testManifest,
  manifestStatuses = [200],
  historyPayloads = playerHistories,
  historyStatuses = {},
  dataVersionPayload = {
    uploaded_at: "2026-04-06T00:00:00.000Z",
    prefix: "latest",
    git_sha: "abcdef1234567890",
    manifest: {
      player_count: testManifest.players.length,
      metric_count: testManifest.metadata.metrics.length,
      selection_mode: testManifest.metadata.selection_mode ?? null
    }
  }
}: {
  manifestPayload?: unknown;
  manifestStatuses?: number[];
  historyPayloads?: Record<string, unknown>;
  historyStatuses?: Record<string, number>;
  dataVersionPayload?: unknown | null;
} = {}) {
  let manifestRequestCount = 0;
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);

    if (url.includes("/players_manifest.json")) {
      const status = manifestStatuses[Math.min(manifestRequestCount, manifestStatuses.length - 1)] ?? 200;
      manifestRequestCount += 1;
      if (status >= 400) {
        return Promise.resolve(jsonResponse({error: "manifest failed"}, {status}));
      }
      return Promise.resolve(jsonResponse(manifestPayload));
    }

    if (url.includes("/data-version.json")) {
      if (dataVersionPayload == null) {
        return Promise.resolve(jsonResponse({error: "version missing"}, {status: 404}));
      }
      return Promise.resolve(jsonResponse(dataVersionPayload));
    }

    const historyId = Object.keys(historyPayloads).find((id) => url.includes(`/player-history/${id}.json`));
    if (historyId) {
      const status = historyStatuses[historyId] ?? 200;
      if (status >= 400) {
        return Promise.resolve(jsonResponse({error: "history failed"}, {status}));
      }
      return Promise.resolve(jsonResponse(historyPayloads[historyId]));
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

    expect(await screen.findByRole("button", {name: "Remove Mike Trout (2011-2024)"})).toBeInTheDocument();
    expect(await screen.findByRole("button", {name: "Remove Clayton Kershaw (2008-2025)"})).toBeInTheDocument();
    expect(await screen.findByRole("button", {name: "Remove Mookie Betts (2014-2025)"})).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toHaveValue("rbi");
    expect(screen.queryByText("Loading selected player histories…")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("MVP-caliber season.")).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("players_manifest.json"), expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/player-history/fg-10155.json"), expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/player-history/fg-2036.json"), expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/player-history/fg-13611.json"), expect.any(Object));
  });

  it("restores selected players and metric from the URL", async () => {
    installFetchMock();
    window.history.replaceState({}, "", "/?players=fg-2036,fg-19755&metric=avg");

    render(<App />);

    await screen.findByRole("heading", {name: "Career arcs, season by season."});

    expect(screen.getByRole("combobox")).toHaveValue("avg");
    expect(await screen.findByRole("button", {name: "Remove Clayton Kershaw (2008-2025)"})).toBeInTheDocument();
    expect(await screen.findByRole("button", {name: "Remove Aaron Judge (2016-2025)"})).toBeInTheDocument();
    expect(screen.queryByRole("button", {name: "Remove Mike Trout (2011-2024)"})).not.toBeInTheDocument();
  });

  it("shows a retry state when manifest fetch fails", async () => {
    const fetchMock = installFetchMock({manifestStatuses: [500, 200]});
    const user = userEvent.setup();
    window.history.replaceState({}, "", "/");

    render(<App />);

    expect(await screen.findByText("Manifest request failed: Failed to load manifest: 500.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", {name: "Retry manifest request"}));

    await screen.findByRole("heading", {name: "Career arcs, season by season."});
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("players_manifest.json"), expect.any(Object));
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("players_manifest.json")).length).toBe(2);
  });

  it("shows an empty selection state when no default players exist in the manifest", async () => {
    installFetchMock({
      manifestPayload: {
        ...testManifest,
        players: testManifest.players.filter((player) => !["Mike Trout", "Clayton Kershaw", "Mookie Betts"].includes(player.n))
      }
    });
    window.history.replaceState({}, "", "/");

    render(<App />);

    await screen.findByRole("heading", {name: "Career arcs, season by season."});
    expect(
      await screen.findByText("No players selected yet. Search and add players above to load their season histories.")
    ).toBeInTheDocument();
  });

  it("shows a player-history fetch error state with retry", async () => {
    installFetchMock({
      historyStatuses: {"fg-2036": 404}
    });
    window.history.replaceState({}, "", "/");

    render(<App />);

    expect(
      await screen.findByText("Player history request failed: Failed to load player history for Clayton Kershaw: 404")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", {name: "Retry player history request"})).toBeInTheDocument();
  });
});
