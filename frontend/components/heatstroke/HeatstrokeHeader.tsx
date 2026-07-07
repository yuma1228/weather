"use client";

import RiskLegend from "./RiskLegend";
import { MAX_WINDOW_HOURS } from "../../lib/config";
import { RISK } from "../../lib/risk";
import type { WeatherPayload } from "../../lib/types";

interface Props {
  payload: WeatherPayload | null;
  windowHours: number;
  onWindowHoursChange: (h: number) => void;
}

export default function HeatstrokeHeader({
  payload,
  windowHours,
  onWindowHoursChange,
}: Props) {
  return (
    <div className="flex flex-wrap items-center gap-4 border-b border-slate-700 bg-slate-800 px-4 py-2.5">

      {payload?.hottest && (
        <div className="text-[13px]">
          最高WBGT: <b className="text-red-400">{payload.hottest.name}</b>{" "}
          {payload.hottest.wbgt}℃（{RISK[payload.hottest.risk_level].label}）
        </div>
      )}

      <label className="ml-auto flex items-center gap-1 text-xs text-slate-300">
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

      <RiskLegend counts={payload?.risk_counts} />
    </div>
  );
}
