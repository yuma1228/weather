// 降水量(mm/h)→ 色と表示。気象庁の降水強度カラーに準拠(簡略版)。
// [しきい値(mm/h), 色, ラベル] を強い順に並べる。
export type RainLevel = [threshold: number, color: string, label: string];

export const RAIN_LEVELS: RainLevel[] = [
  [30, "#b40068", "30mm〜 猛烈な雨"],
  [20, "#ff2800", "20–30 非常に激しい"],
  [10, "#ff9900", "10–20 激しい雨"],
  [5, "#faf500", "5–10 やや強い"],
  [1, "#0041ff", "1–5 弱い雨"],
  [0.1, "#66ccff", "0.1–1 ごく弱い"],
];

// 降水量から色を返す。0mm(降水なし)や欠測は null。
export function rainColor(precip: number | null | undefined): string | null {
  if (precip == null) return null;
  for (const [th, color] of RAIN_LEVELS) {
    if (precip >= th) return color;
  }
  return null;
}

// 0.1mm/h 以上を「降水中」とみなす。
export function isRaining(precip: number | null | undefined): boolean {
  return precip != null && precip >= 0.1;
}
