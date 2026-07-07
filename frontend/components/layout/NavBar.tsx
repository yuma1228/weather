"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useWeatherStream } from "../../hooks/useWeatherStream";

const LINKS = [
  { href: "/heatstroke", label: "熱中症リスク" },
  { href: "/rain", label: "雨雲レーダー" },
];

// 全ページ共通のナビゲーション。現在ページをハイライトする。
export default function NavBar() {
  const pathname = usePathname();
  const { payload } = useWeatherStream();

  return (
    <nav className="flex items-center gap-1 border-b border-slate-700 bg-slate-950 px-4 py-2">
      <span className="mr-4 text-sm font-bold text-slate-300">気象モニタ</span>
      {LINKS.map((l) => {
        const active = pathname === l.href;
        return (
          <Link
            key={l.href}
            href={l.href}
            className={`rounded px-3 py-1 text-sm ${
              active
                ? "bg-slate-700 text-white"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {l.label}
          </Link>
        );
      })}
      <div className="ml-auto text-lg font-semibold tabular-nums text-slate-200">
        {payload?.datetime ?? "接続待ち…"}
      </div>
    </nav>
  );
}
