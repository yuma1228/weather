"use client";

import { CircleMarker, Popup } from "react-leaflet";
import { rainColor, isRaining } from "../../lib/rain";
import { fmt } from "../../lib/format";
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

// 全地点の観測を降水量で表示。雨の地点は強度で色分け&大きく、無降水は小さな灰点。
export default function RainMarkers({
  observations = [],
}: {
  observations?: Observation[];
}) {
  const plottable = observations.filter(
    (o) => o != null && o.lat != null && o.lon != null
  );

  return (
    <>
      {plottable.map((o) => {
        const raining = isRaining(o.precip);
        const color = rainColor(o.precip);
        return (
          <CircleMarker
            key={o.station_id}
            center={[o.lat as number, o.lon as number]}
            radius={4}
            pathOptions={{
              color: "#0b1220",
              weight: raining ? 1 : 0,
              fillColor: raining && color ? color : "#475569",
              fillOpacity: raining ? 0.85 : 0.3,
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
                    <Row label="気温" value={fmt(o.temp, "℃")} />
                    <Row label="湿度" value={fmt(o.humidity, "%")} />
                    <Row label="風速" value={fmt(o.wind_speed, "m/s")} />
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
