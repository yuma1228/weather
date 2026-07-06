"use client";

import dynamic from "next/dynamic";

// Leaflet は window に依存するため SSR を無効化してクライアントのみで描画する
const RainMap = dynamic(() => import("../../components/rain/RainMap"), {
  ssr: false,
  loading: () => <div className="p-5">地図を読み込み中…</div>,
});

export default function Page() {
  return <RainMap />;
}
