"use client";

import { RISK, RISK_ORDER } from "../../lib/risk";

// 「欠測」は雨専用のアメダスで数千件になり熱中症ページでは無意味なので凡例から外す
const LEVELS = RISK_ORDER.filter((k) => k !== "unknown");

// 危険度の凡例。各ランクの地点数(counts)があれば併記する。
export default function RiskLegend({ counts = {} }) {
  return (
    <div className="ml-auto flex flex-wrap gap-2.5">
      {LEVELS.map((k) => (
        <span className="flex items-center gap-1.5 text-xs" key={k}>
          <span
            className="inline-block h-3 w-3 rounded-full"
            style={{ background: RISK[k].color }}
          />
          {RISK[k].label}
          {counts[k] != null ? `(${counts[k]})` : ""}
        </span>
      ))}
    </div>
  );
}
