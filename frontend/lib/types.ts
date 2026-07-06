// バックエンド(client.py)が SSE で流してくる加工済みスナップショットの型。
// フロント全体でこの型を共有する。

// WBGT 危険度のランク。client.py の RISK_LEVELS と対応。
export type RiskLevel =
  | "danger"
  | "severe"
  | "warning"
  | "caution"
  | "safe"
  | "unknown";

// 1地点の観測レコード(生の観測値 + 地点メタ + WBGT 加工結果)。
// 欠測やアメダス(湿度・日射なし)があるため数値系はすべて null を許容する。
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
  // 地点メタ(server 側で station_meta を merge)
  lat: number | null;
  lon: number | null;
  elev: number | null;
  type?: string;
  // client.py の annotate() が付与する加工結果
  wbgt: number | null;
  risk_level: RiskLevel;
  risk_label: string;
}

// 最高WBGT地点のサマリ。
export interface Hottest {
  station_id: string;
  name: string;
  wbgt: number | null;
  risk_label: string;
}

// /stream (と /now) が返すスナップショット全体。
export interface WeatherPayload {
  datetime: string | null;
  index: number;
  total: number;
  step_interval_sec: number;
  count: number;
  risk_counts: Partial<Record<RiskLevel, number>>;
  hottest: Hottest | null;
  observations: Observation[];
}
