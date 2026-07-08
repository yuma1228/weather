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

  const tempPoints = historySlice
    .map((p) => p.temp)
    .filter((v): v is number => v != null);
  const minTemp = Math.min(...tempPoints, observation.temp ?? Infinity);
  const maxTemp = Math.max(...tempPoints, observation.temp ?? -Infinity);
  const tempRange = maxTemp - minTemp || 1;
  const avgTemp = tempPoints.length
    ? Math.round((tempPoints.reduce((a, b) => a + b, 0) / tempPoints.length) * 10) / 10
    : null;

  const precipPoints = historySlice
    .map((p) => p.precip)
    .filter((v): v is number => v != null);
  const avgPrecip = precipPoints.length
    ? Math.round((precipPoints.reduce((a, b) => a + b, 0) / precipPoints.length) * 10) / 10
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
        <section className="mt-1 rounded-md border border-slate-800 bg-slate-900/60 p-3">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-slate-100">降水推移</h2>
            <span className="text-xs text-slate-400">
              {loading
                ? "更新中"
                : error
                  ? "履歴API未接続"
                  : `平均 ${fmt(avgPrecip, "mm/h")}`}
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
          {historySlice.length > 0 && (
            <div className="mt-1 flex gap-1 text-[10px] text-slate-500">
              {historySlice.map((p, i) => (
                <div key={p.datetime} className="min-w-0 flex-1 text-center">
                  {i % 6 === 0 ? p.datetime.slice(11, 16) : ""}
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="mt-3 rounded-md border border-slate-800 bg-slate-900/60 p-3">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-slate-100">気温推移</h2>
            <span className="text-xs text-slate-400">
              平均 {fmt(avgTemp, "℃")}
            </span>
          </div>
          <div className="mt-3 h-16 rounded bg-slate-950 p-2">
            {tempPoints.length > 1 ? (
              <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-full w-full">
                <polyline
                  points={tempPoints
                    .map((v, i) => {
                      const x = (i / (tempPoints.length - 1)) * 100;
                      const y = 100 - ((v - minTemp) / tempRange) * 100;
                      return `${x},${y}`;
                    })
                    .join(" ")}
                  fill="none"
                  stroke="#fb923c"
                  strokeWidth={2}
                  vectorEffect="non-scaling-stroke"
                />
              </svg>
            ) : (
              <div className="flex h-full w-full items-center justify-center text-xs text-slate-500">
                履歴がたまるとここに気温推移が出ます
              </div>
            )}
          </div>
          {historySlice.length > 0 && (
            <div className="mt-1 flex gap-1 text-[10px] text-slate-500">
              {historySlice.map((p, i) => (
                <div key={p.datetime} className="min-w-0 flex-1 text-center">
                  {i % 6 === 0 ? p.datetime.slice(11, 16) : ""}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </aside>
  );
}
