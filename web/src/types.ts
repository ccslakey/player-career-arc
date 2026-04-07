export type MetricFormat = "average" | "integer" | "decimal" | string;

export interface MetricDefinition {
  key: string;
  label: string;
  format: MetricFormat;
}

export interface DatasetMetadata {
  generated_at?: string;
  compact?: boolean;
  manifest?: boolean;
  metric_order?: string[];
  metrics: MetricDefinition[];
  notes?: string[];
  selection_mode?: string;
}

export interface ManifestPlayerEntry {
  i: string;
  n: string;
  f?: number | null;
  y: [number, number];
  r?: string;
}

export interface ManifestPayload {
  metadata: DatasetMetadata;
  players: ManifestPlayerEntry[];
}

export interface EventAnnotation {
  type?: string | null;
  label?: string | null;
  note?: string | null;
  source?: string | null;
  confidence?: "high" | "medium" | "low" | string | null;
  source_url?: string | null;
  event_id?: string | null;
  event_origin?: string | null;
}

export type CompactEventRow = [
  type: string | null,
  label: string | null,
  note: string | null,
  source?: string | null,
  confidence?: string | null,
  sourceUrl?: string | null,
  eventId?: string | null,
  eventOrigin?: string | null
];

export interface SeasonRecord {
  year: number;
  player_type: string | null;
  team: string | null;
  stats: Record<string, number | null>;
  events: EventAnnotation[];
  summary: string;
}

export interface PlayerRecord {
  player_key?: string | null;
  name: string;
  fangraphs_id?: number | null;
  seasons: SeasonRecord[];
}

export interface CompactPlayerHistoryPayload {
  k?: string | null;
  n: string;
  f?: number | null;
  s: Array<
    [
      year: number,
      playerType: string | null,
      team: string | null,
      statValues?: Array<number | null>,
      eventValues?: Array<CompactEventRow | EventAnnotation>,
      summary?: string
    ]
  >;
}

export interface CompactDatasetPayload {
  metadata: DatasetMetadata;
  players: CompactPlayerHistoryPayload[];
}

export interface PlayerOption {
  value: string;
  label: string;
  searchText: string;
}

export interface TooltipDatum extends SeasonRecord {
  playerName: string;
  value: number;
}
