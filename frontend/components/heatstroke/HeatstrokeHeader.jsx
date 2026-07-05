"use client";

import Clock from "../common/Clock";
import ConnectionBadge from "../common/ConnectionBadge";
import RiskLegend from "./RiskLegend";

// 熱中症ページ上部のバー: タイトル・時刻・最高WBGT地点・凡例・接続状態。
export default function HeatstrokeHeader({ payload, connected }) {
  return (
    <div className="flex flex-wrap items-center gap-5 border-b border-slate-700 bg-slate-800 px-4 py-2.5">
      <h1 className="m-0 text-base font-bold">熱中症リスク</h1>

      <Clock payload={payload} />

      {payload?.hottest && (
        <div className="text-[13px]">
          最高WBGT: <b className="text-red-400">{payload.hottest.name}</b>{" "}
          {payload.hottest.wbgt}℃（{payload.hottest.risk_label}）
        </div>
      )}

      <RiskLegend counts={payload?.risk_counts} />
      <ConnectionBadge connected={connected} />
    </div>
  );
}
