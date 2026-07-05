// client.py の RISK_LEVELS と対応する表示設定(色・順序)
export const RISK = {
  danger:  { color: "#7e22ce", label: "危険" },        // ≥31
  severe:  { color: "#dc2626", label: "厳重警戒" },    // 28–31
  warning: { color: "#f97316", label: "警戒" },        // 25–28
  caution: { color: "#facc15", label: "注意" },        // 21–25
  safe:    { color: "#3b82f6", label: "ほぼ安全" },    // <21
  unknown: { color: "#64748b", label: "欠測" },
};

// 凡例・集計の表示順(危険→安全)
export const RISK_ORDER = ["danger", "severe", "warning", "caution", "safe", "unknown"];

export function riskColor(level) {
  return (RISK[level] || RISK.unknown).color;
}
