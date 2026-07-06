// 値+単位の表示(欠測は「―」)。ページ共通で使う。
export function fmt(v: number | string | null | undefined, unit: string): string {
  return v == null ? "―" : `${v} ${unit}`;
}
