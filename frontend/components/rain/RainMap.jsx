"use client";

import BaseMap from "../common/BaseMap";
import { useWeatherStream } from "../../lib/hooks/useWeatherStream";
import RainHeader from "./RainHeader";
import RainMarkers from "./RainMarkers";

// 雨雲レーダーページ本体。SSE購読 → ヘッダ + 地図(降水量マーカー)。
export default function RainMap() {
  const { payload, connected } = useWeatherStream();

  return (
    <div className="flex h-full flex-col">
      <RainHeader payload={payload} connected={connected} />
      <div className="flex-1">
        <BaseMap>
          <RainMarkers observations={payload?.observations} />
        </BaseMap>
      </div>
    </div>
  );
}
