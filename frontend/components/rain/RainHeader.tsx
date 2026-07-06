"use client";

import Clock from "../common/Clock";
import RainLegend from "./RainLegend";
import { isRaining } from "../../lib/rain";
import type { Observation, WeatherPayload } from "../../lib/types";

interface Props {
  payload: WeatherPayload | null;
  connected: boolean;
}

// 雨ページ上部のバー: タイトル・時刻・降水中地点数/最大雨量・凡例・接続状態。
export default function RainHeader({ payload, connected }: Props) {
  const obs = payload?.observations ?? [];
  const raining = obs.filter((o) => isRaining(o.precip));
  const heaviest = raining.reduce<Observation | null>(
    (max, o) =>
      max == null || (o.precip ?? 0) > (max.precip ?? 0) ? o : max,
    null
  );

  return (
    <div className="flex flex-wrap items-center gap-5 border-b border-slate-700 bg-slate-800 px-4 py-2.5">
      <h1 className="m-0 text-base font-bold">雨雲レーダー</h1>

      <Clock payload={payload} />

      <div className="text-[13px]">
        降水中: <b className="text-sky-400">{raining.length}</b> 地点
        {heaviest && (
          <>
            {" "}
            / 最大 <b className="text-sky-300">{heaviest.precip}mm</b>（
            {heaviest.name}）
          </>
        )}
      </div>

      <RainLegend />
    </div>
  );
}
