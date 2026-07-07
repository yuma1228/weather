"use client";

import RainLegend from "./RainLegend";
import { MAX_WINDOW_HOURS } from "../../lib/config";
import type { WeatherPayload } from "../../lib/types";

interface Props {
  payload: WeatherPayload | null;
  windowHours: number;
  onWindowHoursChange: (h: number) => void;
}
export default function RainHeader({
  payload,
  windowHours,
  onWindowHoursChange,
}: Props) {
  const wettest = payload?.wettest;

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-slate-700 bg-slate-800 px-4 py-2.5">

      <div className="text-lg font-semibold tabular-nums">
        {payload?.datetime ?? "接続待ち…"}
      </div>

      <div className="text-[12px]">
        降水中: <b className="text-sky-400">{payload?.raining_count ?? 0}</b> 地点
        {wettest && (
          <>
            {" "}
            / 最大 <b className="text-sky-300">{wettest.precip}mm</b>（
            {wettest.name}）
          </>
        )}
      </div>

      <label className="flex items-center gap-1 text-xs ml-auto text-slate-300">
          window:
        <input
          type="number"
          min={1}
          max={MAX_WINDOW_HOURS}
          value={windowHours}
          onChange={(e) => onWindowHoursChange(Number(e.target.value) || 1)}
          className="w-14 rounded bg-slate-700 px-1 py-0.5 text-right"
        />
        時間
      </label>

      <RainLegend />
    </div>
  );
}
