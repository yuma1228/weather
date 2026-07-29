"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "../lib/config";
import type { StationForecast } from "../lib/types";

export function useStationForecast(
  stationId: string | null | undefined,
  datetime: string | null | undefined
) {
  const [forecast, setForecast] = useState<StationForecast | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!stationId || !datetime) {
      setForecast(null);
      setError(null);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    setForecast((current) =>
      current?.station_id === stationId ? current : null
    );
    setError(null);
    setLoading(true);

    (async () => {
      try {
        const params = new URLSearchParams({
          station_id: stationId,
          datetime,
        });
        const response = await fetch(`${API_BASE}/forecast?${params}`, {
          signal: controller.signal,
        });
        const body = await response.json();
        if (!response.ok) {
          throw new Error(
            typeof body?.detail === "string" ? body.detail : "予測を取得できません"
          );
        }
        setForecast(body as StationForecast);
      } catch (cause) {
        if (controller.signal.aborted) return;
        setError(
          cause instanceof Error ? cause.message : "予測を取得できません"
        );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();

    return () => controller.abort();
  }, [stationId, datetime]);

  return { forecast, loading, error };
}
