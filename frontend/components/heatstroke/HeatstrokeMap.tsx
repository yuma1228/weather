"use client";

import BaseMap from "../common/BaseMap";
import { useWeatherStream } from "../../hooks/useWeatherStream";
import HeatstrokeHeader from "./HeatstrokeHeader";
import RiskMarkers from "./RiskMarkers";

// 熱中症リスクページ本体。SSE購読 → ヘッダ + 地図(WBGTマーカー)。
export default function HeatstrokeMap() {
  const { payload } = useWeatherStream();

  return (
    <div className="flex h-full flex-col">
      <HeatstrokeHeader payload={payload} />
      <div className="flex-1">
        <BaseMap>
          <RiskMarkers observations={payload?.observations} />
        </BaseMap>
      </div>
    </div>
  );
}
