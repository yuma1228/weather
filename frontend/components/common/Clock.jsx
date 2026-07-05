"use client";

// 現在の仮想時刻と進捗(何番目 / 全体)を表示する。両ページ共通。
export default function Clock({ payload }) {
  return (
    <div>
      <div className="text-lg font-semibold tabular-nums">
        {payload?.datetime ?? "接続待ち…"}
      </div>
      <div className="text-xs text-slate-400">
        {payload ? `${payload.index + 1} / ${payload.total} 時刻` : ""}
      </div>
    </div>
  );
}
