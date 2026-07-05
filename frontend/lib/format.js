// 値+単位の表示(欠測は「―」)。ページ共通で使う。
export function fmt(v, unit) {
  return v == null ? "―" : `${v} ${unit}`;
}
