"use client";

import RainLegend from "./RainLegend";
import type { WeatherPayload } from "../../lib/types";

interface Props {
  payload: WeatherPayload | null;
  connected: boolean;
}

export default function RainHeader({ payload }: Props) {
  const wettest = payload?.wettest;

  return (
    <div className="flex flex-wrap items-center gap-5 border-b border-slate-700 bg-slate-800 px-4 py-2.5">
      <h1 className="m-0 text-base font-bold">雨雲レーダー</h1>

      <div className="text-lg font-semibold tabular-nums">
        {payload?.datetime ?? "接続待ち…"}
      </div>

      <div className="text-[13px]">
        降水中: <b className="text-sky-400">{payload?.raining_count ?? 0}</b> 地点
        {wettest && (
          <>
            {" "}
            / 最大 <b className="text-sky-300">{wettest.precip}mm</b>（
            {wettest.name}）
          </>
        )}
      </div>

      <RainLegend />
    </div>
  );
}
