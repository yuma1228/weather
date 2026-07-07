"use client";

import RiskLegend from "./RiskLegend";
import { RISK } from "../../lib/risk";
import type { WeatherPayload } from "../../lib/types";

interface Props {
  payload: WeatherPayload | null;
}

// 熱中症ページ上部のバー: タイトル・時刻・最高WBGT地点・凡例。
export default function HeatstrokeHeader({ payload }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-5 border-b border-slate-700 bg-slate-800 px-4 py-2.5">
      <h1 className="m-0 text-base font-bold">熱中症リスク</h1>

      <div className="text-lg font-semibold tabular-nums">
        {payload?.datetime ?? "接続待ち…"}
      </div>

      {payload?.hottest && (
        <div className="text-[13px]">
          最高WBGT: <b className="text-red-400">{payload.hottest.name}</b>{" "}
          {payload.hottest.wbgt}℃（{RISK[payload.hottest.risk_level].label}）
        </div>
      )}

      <RiskLegend counts={payload?.risk_counts} />
    </div>
  );
}
