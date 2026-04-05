export function parseUrlState({
  search,
  validPlayerIds,
  validMetricKeys,
  fallbackPlayerIds,
  fallbackMetricKey
}: {
  search: string;
  validPlayerIds: Set<string>;
  validMetricKeys: Set<string>;
  fallbackPlayerIds: string[];
  fallbackMetricKey: string;
}): {selectedIds: string[]; metricKey: string} {
  const params = new URLSearchParams(search);
  const selectedIds = (params.get("players") ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter((value) => value && validPlayerIds.has(value));

  const metricKey = params.get("metric") ?? fallbackMetricKey;

  return {
    selectedIds: selectedIds.length ? selectedIds : fallbackPlayerIds,
    metricKey: validMetricKeys.has(metricKey) ? metricKey : fallbackMetricKey
  };
}

export function writeUrlState(selectedIds: string[], metricKey: string): string {
  const params = new URLSearchParams();

  if (selectedIds.length) {
    params.set("players", selectedIds.join(","));
  }

  params.set("metric", metricKey);

  return `${window.location.pathname}?${params.toString()}`;
}
