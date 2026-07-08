"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "../lib/config";

export interface StationHistoryPoint {
  datetime: string;
  temp: number | null;
  precip: number | null;
}

export function useStationHistory(
  stationId: string | null | undefined,
  datetime: string | null | undefined,
  windowHours: number
) {
  const [points, setPoints] = useState<StationHistoryPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!stationId) {
      setPoints([]);
      setError(false);
      return;
    }

    let alive = true;
    setLoading(true);
    setError(false);

    (async () => {
      try {
        const res = await fetch(
          `${API_BASE}/history_series?station_id=${stationId}&hours=${windowHours}`
        );
        if (!res.ok) throw new Error("history_series failed");
        const body = await res.json();
        if (!alive) return;
        setPoints(Array.isArray(body.points) ? body.points : []);
      } catch {
        if (!alive) return;
        setError(true);
        setPoints([]);
      } finally {
        if (alive) setLoading(false);
      }
    })();

    return () => {
      alive = false;
    };
  }, [stationId, datetime, windowHours]);

  return { points, loading, error };
}
