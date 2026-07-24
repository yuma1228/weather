"use client";

import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { WindowPoint } from "./useWindowPrecip";

const REGIONS: [name: string, color: string][] = [
  ["北海道・東北", "#4c9bff"],
  ["関東", "#3ecf8e"],
  ["中部", "#f2c744"],
  ["近畿", "#ff8f3f"],
  ["中国・四国", "#ff5d5d"],
  ["九州・沖縄", "#b07cff"],
];

const PRECIP_FLOOR = 0.05;

// 点1つ = [気温, 表示用降水量(クランプ後), 実際の降水量, 地点名]
type Datum = [number, number, number, string];

function toSeries(points: WindowPoint[]) {
  const byRegion = new Map<string, Datum[]>(REGIONS.map(([name]) => [name, []]));
  for (const point of points) {
    byRegion.get(point.region)?.push([
      point.temp,
      Math.max(point.precip_sum, PRECIP_FLOOR),
      point.precip_sum,
      point.name,
    ]);
  }
  return REGIONS.map(([name, color]) => ({
    name,
    type: "scatter" as const,
    data: byRegion.get(name) ?? [],
    symbolSize: 5,
    large: true,
    itemStyle: { color, opacity: 0.75 },
  }));
}

export function useRainScatterChart(points: WindowPoint[], enabled: boolean) {
  const boxRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const pointsRef = useRef(points);

  // データ更新は series の差し替えだけ。凡例の選択状態は維持される。
  useEffect(() => {
    pointsRef.current = points;
    chartRef.current?.setOption({ series: toSeries(points) });
  }, [points]);

  // 折り畳むと div ごと消えるので、開いたときに現在のデータで作り直す。
  useEffect(() => {
    if (!enabled || !boxRef.current) return;

    const chart = echarts.init(boxRef.current, null, { renderer: "canvas" });
    chartRef.current = chart;
    chart.setOption({
      backgroundColor: "transparent",
      textStyle: { color: "#cbd5e1", fontSize: 11 },
      grid: { left: 48, right: 12, top: 8, bottom: 90 },
      legend: {
        bottom: 4,
        itemWidth: 10,
        itemHeight: 10,
        textStyle: { color: "#cbd5e1", fontSize: 11 },
        data: REGIONS.map(([name]) => name),
      },
      xAxis: {
        type: "value",
        name: "気温 (℃)",
        nameLocation: "middle",
        nameGap: 22,
        min: -10,
        max: 40,
        splitLine: { lineStyle: { color: "#1e293b" } },
      },
      yAxis: {
        type: "log",
        name: "積算降水量 (mm)",
        nameLocation: "middle",
        nameGap: 34,
        min: PRECIP_FLOOR,
        max: 1000,
        axisLabel: {
          formatter: (value: number) =>
            value <= PRECIP_FLOOR ? "0" : String(value),
        },
        splitLine: { lineStyle: { color: "#1e293b" } },
      },
      tooltip: {
        trigger: "item",
        formatter: (params: { data: Datum; seriesName: string }) =>
          `${params.data[3]}（${params.seriesName}）<br/>${params.data[0]}℃ / ${params.data[2]}mm`,
      },
      series: toSeries(pointsRef.current),
    });

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(boxRef.current);

    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, [enabled]);

  return boxRef;
}
