import type { Observation } from "./types";

// 地図に置ける観測(緯度経度あり)。type guard で lat/lon を number に絞る。
export type Located = Observation & { lat: number; lon: number };

export function hasCoords(o: Observation): o is Located {
  return o != null && o.lat != null && o.lon != null;
}
