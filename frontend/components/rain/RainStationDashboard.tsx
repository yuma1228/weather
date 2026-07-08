"use client";

import { isRaining, rainColor } from "../../lib/rain";
import { fmt } from "../../lib/format";
import { useStationHistory } from "../../hooks/useStationHistory";
import type { Observation } from "../../lib/types";

interface Props {
  observation: Observation;
  datetime?: string | null;
  windowHours: number;
  onClose: () => void;
}

export default function RainStationDashboard({
  observation,
  datetime,
  windowHours,
  onClose,
}: Props) {
  const { points, loading, error } = useStationHistory(
    observation.station_id,
    datetime,
    windowHours
  );

  const historySlice = points.slice(-24);
  const maxHistoryPrecip = Math.max(
    ...historySlice.map((p) => p.precip ?? 0),
    observation.precip ?? 0,
    0.1
  );
  const rainyFrames = historySlice.filter((p) => isRaining(p.precip)).length;
  const rainyRatio = historySlice.length
    ? Math.round((rainyFrames / historySlice.length) * 100)
    : null;

  return (
    <aside className="absolute bottom-3 left-3 right-3 z-[1000] rounded-md border border-slate-700 bg-slate-950/95 shadow-2xl shadow-black/40 backdrop-blur sm:bottom-3 sm:left-auto sm:top-3 sm:w-[380px]">
      <div className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/95 px-4 py-3 backdrop-blur">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="truncate text-base font-semibold text-slate-50">
              {observation.name}
            </div>
            <div className="mt-0.5 text-xs text-slate-400">
              {observation.station_id}
              {observation.type ? ` / ${observation.type}` : ""}
              {observation.elev != null ? ` / ${observation.elev}m` : ""}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:border-slate-500 hover:text-white"
          >
            閉じる
          </button>
        </div>
      </div>

      <div className="p-4">
        <div className="flex items-end justify-between gap-3">
          <div>
            <div className="text-xs text-slate-400">観測時刻</div>
            <div className="mt-1 text-sm text-slate-200">
              {observation.datetime ?? datetime ?? "―"}
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs text-slate-400">現在</div>
            <div className="mt-1 text-sm font-semibold text-slate-100">
              {fmt(observation.precip, "mm/h")}
            </div>
          </div>
        </div>

        <section className="mt-4 rounded-md border border-slate-800 bg-slate-900/60 p-3">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-slate-100">直近推移</h2>
            <span className="text-xs text-slate-400">
              {loading ? "更新中" : error ? "履歴API未接続" : `${historySlice.length}点`}
            </span>
          </div>
          <div className="mt-3 flex h-24 items-end gap-1 rounded bg-slate-950 p-2">
            {historySlice.length ? (
              historySlice.map((p) => {
                const value = p.precip ?? 0;
                const height = Math.max(5, (value / maxHistoryPrecip) * 100);
                return (
                  <div
                    key={p.datetime}
                    className="min-w-0 flex-1 rounded-t"
                    title={`${p.datetime} / ${fmt(p.precip, "mm/h")}`}
                    style={{
                      height: `${height}%`,
                      backgroundColor: rainColor(p.precip) ?? "#334155",
                      opacity: isRaining(p.precip) ? 0.95 : 0.55,
                    }}
                  />
                );
              })
            ) : (
              <div className="flex h-full w-full items-center justify-center text-xs text-slate-500">
                履歴がたまるとここに降水推移が出ます
              </div>
            )}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-400">
            <div>降水フレーム: {rainyRatio == null ? "―" : `${rainyRatio}%`}</div>
            <div className="text-right">{windowHours}h window</div>
          </div>
        </section>
      </div>
    </aside>
  );
}
