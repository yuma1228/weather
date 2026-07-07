"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "../lib/config";

export function useWindowAvg(
  datetime: string | null | undefined,
  windowHours: number
) {
  const [avgs, setAvgs] = useState<Record<string, number | null>>({});
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    if (!openId) return;
    let alive = true;
    (async () => {
      try {
        const res = await fetch(
          `${API_BASE}/history?station_id=${openId}&hours=${windowHours}`
        );
        const { precip_avg } = await res.json();
        if (alive) setAvgs((p) => ({ ...p, [openId]: precip_avg }));
      } catch {
        /* client 未起動などは無視 */
      }
    })();
    return () => {
      alive = false;
    };
  }, [openId, datetime, windowHours]);

  return {
    avgs,
    open: (id: string) => setOpenId(id),
    close: (id: string) => setOpenId((cur) => (cur === id ? null : cur)),
  };
}
