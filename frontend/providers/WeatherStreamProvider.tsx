"use client";

import {
  createContext,
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

// context はこのファイルの外に出さない。触れるのは下の Provider と useWeatherStream だけ。
// 初期値は SSE の初回フレームが届く前の実状態そのものなので、null を置く必要がない。
const WeatherStreamContext = createContext<WeatherStream>({
  payload: null,
  connected: false,
});

export default function WeatherStreamProvider({
  children,
}: {
  children: ReactNode;
}) {
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

  return (
    <WeatherStreamContext.Provider value={{ payload, connected }}>
      {children}
    </WeatherStreamContext.Provider>
  );
}

// どのページからでも import して使える共有ストリーム。
export const useWeatherStream = () => useContext(WeatherStreamContext);
