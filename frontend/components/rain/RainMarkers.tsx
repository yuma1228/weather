"use client";

import { CircleMarker, Popup } from "react-leaflet";
import { rainColor, isRaining } from "../../lib/rain";
import { fmt } from "../../lib/format";
import { hasCoords } from "../../lib/obs";
import { useWindowAvg } from "../../hooks/useWindowAvg";
import type { Observation } from "../../lib/types";

// ポップアップ内の1行(項目名 + 値)。
function Row({ label, value }: { label: string; value: string }) {
  return (
    <tr>
      <td className="py-px pr-1.5">{label}</td>
      <td className="py-px">{value}</td>
    </tr>
  );
}

export default function RainMarkers({
  observations = [],
  datetime,
  windowHours,
}: {
  observations?: Observation[];
  datetime?: string | null;
  windowHours: number;
}) {
  const { avgs, open, close } = useWindowAvg(datetime, windowHours);

  const plottable = observations.filter(hasCoords);

  return (
    <>
      {plottable.map((o) => {
        const raining = isRaining(o.precip);
        const color = rainColor(o.precip);
        return (
          <CircleMarker
            key={o.station_id}
            center={[o.lat, o.lon]}
            radius={4}
            pathOptions={{
              color: "#0b1220",
              weight: raining ? 1 : 0,
              fillColor: raining && color ? color : "#475569",
              fillOpacity: raining ? 0.85 : 0.3,
            }}
            eventHandlers={{
              popupopen: () => open(o.station_id),
              popupclose: () => close(o.station_id),
            }}
          >
            <Popup>
              <div className="text-slate-800">
                <b className="text-sm">{o.name}</b>（{o.station_id}）<br />
                <span
                  className="text-xl font-bold"
                  style={{ color: raining && color ? color : "#64748b" }}
                >
                  {o.precip ?? "―"} mm/h
                </span>{" "}
                {raining ? "" : "(降水なし)"}
                <table className="mt-1 border-collapse text-xs">
                  <tbody>
                    <Row label="降水" value={fmt(o.precip, "mm")} />
                    <Row
                      label={`平均降水(${windowHours}h)`}
                      value={fmt(avgs[o.station_id], "mm/h")}
                    />
                  </tbody>
                </table>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </>
  );
}
