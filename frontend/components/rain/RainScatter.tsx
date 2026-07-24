"use client";

import { useState } from "react";
import { useRainScatterChart } from "../../hooks/useRainScatterChart";
import { useWindowPrecip } from "../../hooks/useWindowPrecip";

interface Props {
  datetime?: string | null;
  windowHours: number;
}

export default function RainScatter({ datetime, windowHours }: Props) {
  const { points, stale } = useWindowPrecip(datetime, windowHours);
  const [open, setOpen] = useState(true);
  const boxRef = useRainScatterChart(points, open);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="hidden w-8 shrink-0 border-r border-slate-700 bg-slate-900 text-xs text-slate-400 hover:text-slate-100 sm:block"
        title="散布図を開く"
      >
        ▶
      </button>
    );
  }

  return (
    <aside className="hidden w-[360px] shrink-0 flex-col border-r border-slate-700 bg-slate-900 sm:flex">
      <div className="flex items-center gap-2 border-b border-slate-800 px-3 py-2">
        <div className="text-[13px] font-semibold text-slate-100">
          気温 × 直近{windowHours}h降水量
        </div>
        <div className="text-[11px] text-slate-400">
          {stale ? "更新待ち" : `${points.length}地点`}
        </div>
        <button
          onClick={() => setOpen(false)}
          className="ml-auto text-xs text-slate-400 hover:text-slate-100"
          title="閉じる"
        >
          ◀
        </button>
      </div>
      <div ref={boxRef} className="min-h-0 flex-1" />
    </aside>
  );
}
