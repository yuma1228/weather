"use client";

import { useEffect, useState } from "react";
import { STREAM_URL } from "../config";

/**
 * 処理系(client.py)の SSE を購読し、最新の加工済みスナップショットを返す。
 * どのページからでも import して使える。
 *
 * @returns {{ payload: object|null, connected: boolean }}
 */
export function useWeatherStream() {
  const [payload, setPayload] = useState(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const es = new EventSource(STREAM_URL);
    es.onopen = () => setConnected(true);
    es.onmessage = (e) => {
      try {
        setPayload(JSON.parse(e.data));
      } catch (_) {
        /* 壊れたフレームは無視 */
      }
    };
    es.onerror = () => setConnected(false);
    return () => es.close();
  }, []);

  return { payload, connected };
}
