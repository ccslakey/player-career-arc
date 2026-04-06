import {describe, expect, it, vi} from "vitest";
import {fetchManifest, loadSelectedPlayers} from "./historyStore";
import {jsonResponse, playerHistories, testManifest} from "../test/fixtures";

describe("historyStore", () => {
  it("loads the manifest", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(testManifest));
    vi.stubGlobal("fetch", fetchMock);

    const payload = await fetchManifest();

    expect(payload.players).toHaveLength(5);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("reuses cached player history promises", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/data/player-history/fg-10155.json")) {
        return Promise.resolve(jsonResponse(playerHistories["fg-10155"]));
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    const metrics = testManifest.metadata.metrics;
    const metricOrder = testManifest.metadata.metric_order ?? metrics.map((metric) => metric.key);
    const manifestById = new Map(testManifest.players.map((player) => [player.i, player]));
    const historyCache = new Map();

    const first = await loadSelectedPlayers({
      selectedIds: ["fg-10155"],
      manifestById,
      historyCache,
      metricOrder,
      metrics
    });

    const second = await loadSelectedPlayers({
      selectedIds: ["fg-10155"],
      manifestById,
      historyCache,
      metricOrder,
      metrics
    });

    expect(first[0].name).toBe("Mike Trout");
    expect(second[0].name).toBe("Mike Trout");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
