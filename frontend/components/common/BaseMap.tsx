"use client";

import type { ReactNode } from "react";
import { MapContainer, TileLayer } from "react-leaflet";

// 日本全体を映す暗色ベースの地図。マーカー等は children で受け取る。
// 熱中症ページ・雨ページで共通利用する。
export default function BaseMap({ children }: { children?: ReactNode }) {
  return (
    <MapContainer center={[37.5, 137]} zoom={5} preferCanvas style={{ height: "100%" }}>
      <TileLayer
        attribution="&copy; OpenStreetMap, &copy; CARTO"
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />
      {children}
    </MapContainer>
  );
}
