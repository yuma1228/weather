"use client";

import {
  createContext,
  createElement,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { STREAM_URL } from "../lib/config";
import type { WeatherPayload } from "../lib/types";

export interface WeatherStream {
  payload: WeatherPayload | null;
  connected: boolean;
}

const WeatherStreamContext = createContext<WeatherStream | null>(null);

function useWeatherStreamSource(): WeatherStream {
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

export function WeatherStreamProvider({ children }: { children: ReactNode }) {
  const value = useWeatherStreamSource();
  return createElement(WeatherStreamContext.Provider, { value }, children);
}

// どのページからでも import して使える共有ストリーム。
export function useWeatherStream(): WeatherStream {
  const value = useContext(WeatherStreamContext);
  if (!value) {
    throw new Error("useWeatherStream must be used inside WeatherStreamProvider");
  }
  return value;
}
