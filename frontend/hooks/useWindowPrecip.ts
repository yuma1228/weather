"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "../lib/config";

export interface WindowPoint {
  station_id: string;
  name: string;
  region: string;
  temp: number;
  precip_sum: number;
}

export function useWindowPrecip(
  datetime: string | null | undefined,
  windowHours: number
) {
  const [points, setPoints] = useState<WindowPoint[]>([]);
  const [stale, setStale] = useState(false);

  useEffect(() => {
    if (!datetime) return;
    let alive = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/window?hours=${windowHours}`);
        const data: { points: WindowPoint[] } = await res.json();
        if (!alive) return;
        setPoints(data.points);
        setStale(false);
      } catch {
        // client 未起動などは直前のデータを表示したままにする
        if (alive) setStale(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [datetime, windowHours]);

  return { points, stale };
}
