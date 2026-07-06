"use client";

import { useEffect, useState } from "react";
import { STREAM_URL } from "../config";
import type { WeatherPayload } from "../types";

export interface WeatherStream {
  payload: WeatherPayload | null;
  connected: boolean;
}

/**
 * 処理系(client.py)の SSE を購読し、最新の加工済みスナップショットを返す。
 * どのページからでも import して使える。
 */
export function useWeatherStream(): WeatherStream {
  const [payload, setPayload] = useState<WeatherPayload | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const es = new EventSource(STREAM_URL);
    es.onopen = () => setConnected(true);
    es.onmessage = (e: MessageEvent<string>) => {
      try {
        setPayload(JSON.parse(e.data) as WeatherPayload);
      } catch {
        /* 壊れたフレームは無視 */
      }
    };
    es.onerror = () => setConnected(false);
    return () => es.close();
  }, []);

  return { payload, connected };
}
