"use client";

import { useState } from "react";
import BaseMap from "../common/BaseMap";
import { useWeatherStream } from "../../hooks/useWeatherStream";
import RainHeader from "./RainHeader";
import RainMarkers from "./RainMarkers";
import RainStationDashboard from "./RainStationDashboard";
import { MAX_WINDOW_HOURS } from "../../lib/config";

export default function RainMap() {
  const { payload } = useWeatherStream();
  const [windowHours, setWindowHours] = useState(MAX_WINDOW_HOURS);
  const [selectedStationId, setSelectedStationId] = useState<string | null>(null);
  const selectedObservation =
    payload?.observations.find((o) => o.station_id === selectedStationId) ?? null;

  return (
    <div className="flex h-full flex-col">
      <RainHeader
        payload={payload}
        windowHours={windowHours}
        onWindowHoursChange={setWindowHours}
      />
      <div className="relative flex-1">
        <BaseMap>
          <RainMarkers
            observations={payload?.observations}
            datetime={payload?.datetime}
            windowHours={windowHours}
            onShowDetails={(observation) => setSelectedStationId(observation.station_id)}
          />
        </BaseMap>
        {payload && selectedObservation && (
          <RainStationDashboard
            observation={selectedObservation}
            datetime={payload.datetime}
            windowHours={windowHours}
            onClose={() => setSelectedStationId(null)}
          />
        )}
      </div>
    </div>
  );
}
