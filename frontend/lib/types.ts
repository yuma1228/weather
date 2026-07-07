export type RiskLevel =
  | "danger"
  | "severe"
  | "warning"
  | "caution"
  | "safe"
  | "unknown";

export interface Observation {
  datetime: string;
  station_id: string;
  name: string;
  temp: number | null;
  precip: number | null;
  humidity: number | null;
  solar: number | null;
  sunshine: number | null;
  cloud: string | null;
  wind_dir: string | null;
  wind_speed: number | null;
  vapor_pressure: number | null;
  dew_point: number | null;
  lat: number | null;
  lon: number | null;
  elev: number | null;
  type?: string;
  wbgt: number | null;
  risk_level: RiskLevel;
  risk_label: string;
}

export interface Hottest {
  station_id: string;
  name: string;
  wbgt: number | null;
  risk_label: string;
}

export interface Wettest {
  station_id: string;
  name: string;
  precip: number | null;
}

export interface WeatherPayload {
  datetime: string | null;
  risk_counts: Partial<Record<RiskLevel, number>>;
  hottest: Hottest | null;
  raining_count: number;
  wettest: Wettest | null;
  observations: Observation[];
}
