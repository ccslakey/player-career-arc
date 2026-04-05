import {format as d3Format} from "d3";
import type {MetricDefinition} from "../types";

export function formatMetric(metric: MetricDefinition, value: number): string {
  if (metric.format === "integer") {
    return d3Format("d")(value);
  }

  if (metric.format === "decimal") {
    return d3Format(".1f")(value);
  }

  return d3Format(".3f")(value);
}
