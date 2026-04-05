import {useEffect, useMemo, useRef, useState} from "react";
import {CareerArcChart} from "./components/CareerArcChart";
import {PlayerPicker} from "./components/PlayerPicker";
import {SeasonTable} from "./components/SeasonTable";
import {fetchManifest, loadSelectedPlayers} from "./lib/historyStore";
import {parseUrlState, writeUrlState} from "./lib/urlState";
import type {ManifestPayload, MetricDefinition, PlayerOption, PlayerRecord} from "./types";

const DEFAULT_PLAYER_NAMES = ["Mike Trout", "Clayton Kershaw", "Mookie Betts"];
const MAX_SELECTIONS = 10;

export default function App() {
  const [manifest, setManifest] = useState<ManifestPayload | null>(null);
  const [manifestError, setManifestError] = useState<string | null>(null);
  const [manifestLoading, setManifestLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [metricKey, setMetricKey] = useState("war");
  const [hasInitializedState, setHasInitializedState] = useState(false);
  const [players, setPlayers] = useState<PlayerRecord[]>([]);
  const [playersError, setPlayersError] = useState<string | null>(null);
  const [playersLoading, setPlayersLoading] = useState(false);
  const historyCache = useRef(new Map<string, Promise<PlayerRecord>>());

  useEffect(() => {
    const controller = new AbortController();

    setManifestLoading(true);
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

    return () => controller.abort();
  }, []);

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

    const controller = new AbortController();
    setPlayersLoading(true);
    setPlayersError(null);

    loadSelectedPlayers({
      selectedIds: selectedIds.slice(0, MAX_SELECTIONS),
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
          setPlayersError(error.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setPlayersLoading(false);
        }
      });

    return () => controller.abort();
  }, [hasInitializedState, manifest, manifestById, metricOrder, metrics, selectedIds]);

  const activeMetric = useMemo<MetricDefinition | null>(
    () => metrics.find((metric) => metric.key === metricKey) ?? metrics[0] ?? null,
    [metricKey, metrics]
  );

  if (manifestLoading) {
    return <main className="page-shell"><div className="panel">Loading player manifest…</div></main>;
  }

  if (manifestError || !manifest) {
    return (
      <main className="page-shell">
        <div className="panel error-panel">Manifest error: {manifestError ?? "Unknown error"}</div>
      </main>
    );
  }

  return (
    <main className="page-shell">
      <section className="hero">
        <p className="eyebrow">React parity migration</p>
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

      {playersError ? <div className="panel error-panel">{playersError}</div> : null}
      {playersLoading ? <div className="panel">Loading selected player histories…</div> : null}

      {activeMetric ? <CareerArcChart players={players} metric={activeMetric} /> : null}
      {activeMetric ? <SeasonTable players={players} metric={activeMetric} /> : null}

      <div className="panel footer-note">
        <p className="note">
          Mode: {manifest.metadata.selection_mode}. Notes: {(manifest.metadata.notes ?? []).join(" ")}
        </p>
      </div>
    </main>
  );
}
