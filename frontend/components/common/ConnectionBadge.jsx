"use client";

// SSE の接続状態バッジ(LIVE / 切断)。両ページ共通。
export default function ConnectionBadge({ connected }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs ${
        connected ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"
      }`}
    >
      {connected ? "● LIVE" : "○ 切断"}
    </span>
  );
}
