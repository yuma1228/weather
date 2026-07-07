"use client";

import { useEffect, useState } from "react";
import { STREAM_URL } from "../config";
import type { WeatherPayload } from "../types";

export interface WeatherStream {
  payload: WeatherPayload | null;
  connected: boolean;
}

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
      }
    };
    es.onerror = () => setConnected(false);
    return () => es.close();
  }, []);

  return { payload, connected };
}
