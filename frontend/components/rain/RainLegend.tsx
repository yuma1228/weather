"use client";

import { RAIN_LEVELS } from "../../lib/rain";

export default function RainLegend() {
  return (
    <div className="ml-auto flex flex-wrap gap-2.5">
      {RAIN_LEVELS.map(([th, color, label]) => (
        <span className="flex items-center gap-1.5 text-xs" key={th}>
          <span
            className="inline-block h-3 w-3 rounded-full"
            style={{ background: color }}
          />
          {label}
        </span>
      ))}
      <span className="flex items-center gap-1.5 text-xs">
        <span className="inline-block h-3 w-3 rounded-full bg-slate-600" />
        降水なし
      </span>
    </div>
  );
}
