"use client";

import { useState } from "react";
import BaseMap from "../common/BaseMap";
import { useWeatherStream } from "../../hooks/useWeatherStream";
import RainHeader from "./RainHeader";
import RainMarkers from "./RainMarkers";
import { MAX_WINDOW_HOURS } from "../../lib/config";

export default function RainMap() {
  const { payload } = useWeatherStream();
  const [windowHours, setWindowHours] = useState(MAX_WINDOW_HOURS);

  return (
    <div className="flex h-full flex-col">
      <RainHeader
        payload={payload}
        windowHours={windowHours}
        onWindowHoursChange={setWindowHours}
      />
      <div className="flex-1">
        <BaseMap>
          <RainMarkers
            observations={payload?.observations}
            datetime={payload?.datetime}
            windowHours={windowHours}
          />
        </BaseMap>
      </div>
    </div>
  );
}
