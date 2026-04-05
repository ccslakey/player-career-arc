import {describe, expect, it} from "vitest";
import {parseUrlState} from "./urlState";

describe("parseUrlState", () => {
  it("prefers valid URL values and falls back when missing", () => {
    const state = parseUrlState({
      search: "?players=fg-1,fg-2&metric=war",
      validPlayerIds: new Set(["fg-1", "fg-2", "fg-3"]),
      validMetricKeys: new Set(["war", "ops"]),
      fallbackPlayerIds: ["fg-3"],
      fallbackMetricKey: "ops"
    });

    expect(state.selectedIds).toEqual(["fg-1", "fg-2"]);
    expect(state.metricKey).toBe("war");
  });

  it("falls back when URL params are invalid", () => {
    const state = parseUrlState({
      search: "?players=bad-id&metric=era",
      validPlayerIds: new Set(["fg-1", "fg-2", "fg-3"]),
      validMetricKeys: new Set(["war", "ops"]),
      fallbackPlayerIds: ["fg-3"],
      fallbackMetricKey: "ops"
    });

    expect(state.selectedIds).toEqual(["fg-3"]);
    expect(state.metricKey).toBe("ops");
  });
});
