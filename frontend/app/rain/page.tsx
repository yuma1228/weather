"use client";

import dynamic from "next/dynamic";

// Leaflet は window に依存するため SSR を無効化してクライアントのみで描画する
const RainMap = dynamic(() => import("../../components/rain/RainMap"), {
  ssr: false,
});

export default function Page() {
  return <RainMap />;
}
