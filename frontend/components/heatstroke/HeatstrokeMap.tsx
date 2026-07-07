"use client";

import { useState } from "react";
import BaseMap from "../common/BaseMap";
import { useWeatherStream } from "../../hooks/useWeatherStream";
import HeatstrokeHeader from "./HeatstrokeHeader";
import RiskMarkers from "./RiskMarkers";
import { MAX_WINDOW_HOURS } from "../../lib/config";

// 熱中症リスクページ本体。SSE購読 → ヘッダ + 地図(WBGTマーカー)。
export default function HeatstrokeMap() {
  const { payload } = useWeatherStream();
  const [windowHours, setWindowHours] = useState(MAX_WINDOW_HOURS);

  return (
    <div className="flex h-full flex-col">
      <HeatstrokeHeader
        payload={payload}
        windowHours={windowHours}
        onWindowHoursChange={setWindowHours}
      />
      <div className="flex-1">
        <BaseMap>
          <RiskMarkers
            observations={payload?.observations}
            datetime={payload?.datetime}
            windowHours={windowHours}
          />
        </BaseMap>
      </div>
    </div>
  );
}
