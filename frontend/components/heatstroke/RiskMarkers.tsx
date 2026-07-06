"use client";

import { CircleMarker, Popup } from "react-leaflet";
import { riskColor } from "../../lib/risk";
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

// 全地点の観測を WBGT 危険度で色分けして表示。WBGTが高いほど大きく。
export default function RiskMarkers({
  observations = [],
}: {
  observations?: Observation[];
}) {
  // 描画対象は「地図に置けて」「WBGTが算出できた」地点のみ。
  // アメダスは湿度・日射が無く WBGT=null になるため、ここで自然に除外される
  // (熱中症ページは官署中心、降水はアメダス込みで雨ページに表示)。
  const plottable = observations.filter(
    (o) => o != null && o.lat != null && o.lon != null && o.wbgt != null
  );

  return (
    <>
      {plottable.map((o) => (
        <CircleMarker
          key={o.station_id}
          center={[o.lat as number, o.lon as number]}
          radius={o.wbgt != null ? 5 + (o.wbgt - 20) * 0.6 : 4}
          pathOptions={{
            color: "#0b1220",
            weight: 1,
            fillColor: riskColor(o.risk_level),
            fillOpacity: o.wbgt != null ? 0.85 : 0.35,
          }}
        >
          <Popup>
            <div className="text-slate-800">
              <b className="text-sm">{o.name}</b>（{o.station_id}）<br />
              <span
                className="text-xl font-bold"
                style={{ color: riskColor(o.risk_level) }}
              >
                WBGT {o.wbgt ?? "―"}
              </span>{" "}
              {o.risk_label}
              <table className="mt-1 border-collapse text-xs">
                <tbody>
                  <Row label="気温" value={fmt(o.temp, "℃")} />
                  <Row label="湿度" value={fmt(o.humidity, "%")} />
                  <Row label="日射" value={fmt(o.solar, "MJ/m²")} />
                  <Row label="風速" value={fmt(o.wind_speed, "m/s")} />
                  <Row label="降水" value={fmt(o.precip, "mm")} />
                </tbody>
              </table>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </>
  );
}
