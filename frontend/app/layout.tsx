import "leaflet/dist/leaflet.css";
import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import NavBar from "../components/layout/NavBar";

export const metadata: Metadata = {
  title: "気象モニタ(熱中症リスク / 雨雲レーダー)",
  description: "WBGT と降水量のリアルタイム可視化",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <div className="flex h-screen flex-col">
          <NavBar />
          <main className="min-h-0 flex-1">{children}</main>
        </div>
      </body>
    </html>
  );
}
