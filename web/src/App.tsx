import {useEffect, useMemo, useRef, useState} from "react";
import {CareerArcChart} from "./components/CareerArcChart";
import {PlayerPicker} from "./components/PlayerPicker";
import {SeasonTable} from "./components/SeasonTable";
import {fetchDataVersion, fetchManifest, loadSelectedPlayers} from "./lib/historyStore";
import {parseUrlState, writeUrlState} from "./lib/urlState";
import type {DataVersionPayload, ManifestPayload, MetricDefinition, PlayerOption, PlayerRecord} from "./types";

const DEFAULT_PLAYER_NAMES = ["Mike Trout", "Clayton Kershaw", "Mookie Betts"];
const MAX_SELECTIONS = 10;

export default function App() {
  const [manifest, setManifest] = useState<ManifestPayload | null>(null);
  const [manifestError, setManifestError] = useState<string | null>(null);
  const [manifestLoading, setManifestLoading] = useState(true);
  const [manifestRequestNonce, setManifestRequestNonce] = useState(0);
  const [dataVersion, setDataVersion] = useState<DataVersionPayload | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [metricKey, setMetricKey] = useState("war");
  const [hasInitializedState, setHasInitializedState] = useState(false);
  const [players, setPlayers] = useState<PlayerRecord[]>([]);
  const [playersError, setPlayersError] = useState<string | null>(null);
  const [playersLoading, setPlayersLoading] = useState(false);
  const [playersRequestNonce, setPlayersRequestNonce] = useState(0);
  const historyCache = useRef(new Map<string, Promise<PlayerRecord>>());

  useEffect(() => {
    const controller = new AbortController();

    setManifest(null);
    setManifestError(null);
    setManifestLoading(true);
    setDataVersion(null);

    fetchManifest(controller.signal)
      .then((payload) => {
        setManifest(payload);
        setManifestError(null);
      })
      .catch((error: Error) => {
        if (controller.signal.aborted) {
          return;
        }
        setManifestError(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setManifestLoading(false);
        }
      });

    fetchDataVersion(controller.signal)
      .then((payload) => {
        if (!controller.signal.aborted) {
          setDataVersion(payload);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setDataVersion(null);
        }
      });

    return () => controller.abort();
  }, [manifestRequestNonce]);

  const metrics = manifest?.metadata.metrics ?? [];
  const metricOrder = useMemo(
    () => manifest?.metadata.metric_order ?? metrics.map((metric) => metric.key),
    [manifest, metrics]
  );
  const manifestById = useMemo(
    () => new Map((manifest?.players ?? []).map((player) => [player.i, player])),
    [manifest]
  );
  const playerOptions = useMemo<PlayerOption[]>(
    () =>
      (manifest?.players ?? []).map((player) => ({
        value: player.i,
        label: `${player.n} (${player.y[0]}-${player.y[1]})`,
        searchText: `${player.n} ${player.f ?? ""} ${player.r ?? ""}`
      })),
    [manifest]
  );

  const defaultPlayerIds = useMemo(
    () =>
      (manifest?.players ?? [])
        .filter((player) => DEFAULT_PLAYER_NAMES.includes(player.n))
        .map((player) => player.i),
    [manifest]
  );

  useEffect(() => {
    if (!manifest || hasInitializedState) {
      return;
    }

    const {selectedIds: initialIds, metricKey: initialMetricKey} = parseUrlState({
      search: window.location.search,
      validPlayerIds: new Set((manifest.players ?? []).map((player) => player.i)),
      validMetricKeys: new Set(metrics.map((metric) => metric.key)),
      fallbackPlayerIds: defaultPlayerIds,
      fallbackMetricKey: metrics.find((metric) => metric.key === "war")?.key ?? metrics[0]?.key ?? "war"
    });

    setSelectedIds(initialIds);
    setMetricKey(initialMetricKey);
    setHasInitializedState(true);
  }, [defaultPlayerIds, hasInitializedState, manifest, metrics]);

  useEffect(() => {
    if (!hasInitializedState) {
      return;
    }

    window.history.replaceState({}, "", writeUrlState(selectedIds.slice(0, MAX_SELECTIONS), metricKey));
  }, [hasInitializedState, metricKey, selectedIds]);

  useEffect(() => {
    if (!manifest || !hasInitializedState) {
      return;
    }

    const boundedSelectedIds = selectedIds.slice(0, MAX_SELECTIONS);
    if (!boundedSelectedIds.length) {
      setPlayers([]);
      setPlayersError(null);
      setPlayersLoading(false);
      return;
    }

    const controller = new AbortController();
    setPlayersLoading(true);
    setPlayersError(null);

    loadSelectedPlayers({
      selectedIds: boundedSelectedIds,
      manifestById,
      historyCache: historyCache.current,
      metricOrder,
      metrics,
      signal: controller.signal
    })
      .then((nextPlayers) => {
        if (!controller.signal.aborted) {
          setPlayers(nextPlayers);
        }
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) {
          setPlayers([]);
          setPlayersError(error.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setPlayersLoading(false);
        }
      });

    return () => controller.abort();
  }, [hasInitializedState, manifest, manifestById, metricOrder, metrics, playersRequestNonce, selectedIds]);

  const activeMetric = useMemo<MetricDefinition | null>(
    () => metrics.find((metric) => metric.key === metricKey) ?? metrics[0] ?? null,
    [metricKey, metrics]
  );
  const manifestHasNoPlayers = Boolean(manifest && manifest.players.length === 0);
  const manifestHasNoMetrics = Boolean(manifest && metrics.length === 0);
  const noPlayersSelected = hasInitializedState && selectedIds.length === 0;
  const noPlayerHistoriesFound =
    hasInitializedState && selectedIds.length > 0 && !playersLoading && !playersError && players.length === 0;
  const showDataViews = Boolean(activeMetric) && !playersLoading && !playersError && players.length > 0;

  if (manifestLoading) {
    return (
      <main className="page-shell">
        <div className="panel state-panel">Loading player manifest…</div>
      </main>
    );
  }

  if (manifestError || !manifest) {
    return (
      <main className="page-shell">
        <div className="panel error-panel state-panel">
          <p>Manifest request failed: {manifestError ?? "Unknown error"}.</p>
          <button
            className="state-action"
            type="button"
            onClick={() => setManifestRequestNonce((value) => value + 1)}
          >
            Retry manifest request
          </button>
        </div>
      </main>
    );
  }

  if (manifestHasNoPlayers || manifestHasNoMetrics) {
    return (
      <main className="page-shell">
        <div className="panel state-panel">
          <p>Manifest loaded, but it is missing required data.</p>
          {manifestHasNoPlayers ? <p className="note">No players were found in `players_manifest.json`.</p> : null}
          {manifestHasNoMetrics ? <p className="note">No metric definitions were found in manifest metadata.</p> : null}
          <button
            className="state-action"
            type="button"
            onClick={() => setManifestRequestNonce((value) => value + 1)}
          >
            Retry manifest request
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="page-shell">
      <section className="hero">
        <h1>Career arcs, season by season.</h1>
        <p>
          Compare up to 10 MLB players across core batting and pitching stats, then hover any point to
          see season context like team changes, injuries, and generated narrative summaries.
        </p>
      </section>

      <section className="controls">
        <div className="panel">
          <h2 className="panel-title">Players</h2>
          <PlayerPicker
            options={playerOptions}
            selectedIds={selectedIds}
            onChange={(nextIds) => setSelectedIds(nextIds.slice(0, MAX_SELECTIONS))}
            maxSelections={MAX_SELECTIONS}
          />
        </div>

        <div className="panel">
          <h2 className="panel-title">Metric</h2>
          <label className="metric-select-label" htmlFor="metric-select">
            Choose a metric
          </label>
          <select
            id="metric-select"
            className="metric-select"
            value={activeMetric?.key ?? ""}
            onChange={(event) => setMetricKey(event.target.value)}
          >
            {metrics.map((metric) => (
              <option key={metric.key} value={metric.key}>
                {metric.label}
              </option>
            ))}
          </select>
        </div>
      </section>

      {selectedIds.length > MAX_SELECTIONS ? (
        <div className="warning">Only the first 10 selected players are shown at once.</div>
      ) : null}

      {playersLoading ? <div className="panel state-panel">Loading selected player histories…</div> : null}
      {playersError ? (
        <div className="panel error-panel state-panel">
          <p>Player history request failed: {playersError}</p>
          <button
            className="state-action"
            type="button"
            onClick={() => setPlayersRequestNonce((value) => value + 1)}
          >
            Retry player history request
          </button>
        </div>
      ) : null}
      {noPlayersSelected ? (
        <div className="panel state-panel">
          No players selected yet. Search and add players above to load their season histories.
        </div>
      ) : null}
      {noPlayerHistoriesFound ? (
        <div className="panel state-panel">
          <p>No player histories were returned for the current selection.</p>
          <button
            className="state-action"
            type="button"
            onClick={() => setPlayersRequestNonce((value) => value + 1)}
          >
            Retry player history request
          </button>
        </div>
      ) : null}

      {showDataViews ? <CareerArcChart players={players} metric={activeMetric!} /> : null}
      {showDataViews ? <SeasonTable players={players} metric={activeMetric!} /> : null}

      <div className="panel footer-note">
        <p className="note">
          Mode: {manifest.metadata.selection_mode}. Notes: {(manifest.metadata.notes ?? []).join(" ")}
        </p>
        <p className="note">Data version: {formatDataVersion(dataVersion)}</p>
      </div>
    </main>
  );
}

function formatDataVersion(dataVersion: DataVersionPayload | null): string {
  if (!dataVersion) {
    return "Unavailable";
  }

  const segments = [dataVersion.prefix];
  if (dataVersion.manifest?.player_count != null) {
    segments.push(`${dataVersion.manifest.player_count.toLocaleString()} players`);
  }
  if (dataVersion.git_sha) {
    segments.push(`sha ${dataVersion.git_sha.slice(0, 7)}`);
  }

  const uploadedAt = new Date(dataVersion.uploaded_at);
  if (!Number.isNaN(uploadedAt.getTime())) {
    segments.push(uploadedAt.toLocaleString());
  }

  return segments.join(" · ");
}
