"use client"

import * as React from "react"
import { ColorType, LineSeries, createChart, type IChartApi, type ISeriesApi, type LineData, type UTCTimestamp } from "lightweight-charts"

import type { PredictResponse } from "@/lib/api"

type Props = {
  prediction: PredictResponse
  baselineClose?: number | null
}

function toUtcTs(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp
}

function getPalette() {
  const isDark = document.documentElement.classList.contains("dark")

  if (isDark) {
    return {
      text: "#fafafa",
      grid: "#27272a",
      border: "#27272a",
      crosshair: "#71717a",
      line: "#60a5fa",
      baseline: "rgba(250,250,250,0.4)",
    }
  }

  return {
    text: "#0a0a0a",
    grid: "#e5e7eb",
    border: "#e5e7eb",
    crosshair: "#a1a1aa",
    line: "#2563eb",
    baseline: "rgba(10,10,10,0.35)",
  }
}

function PredictionCloseChart({ prediction, baselineClose }: Props) {
  const containerRef = React.useRef<HTMLDivElement | null>(null)
  const chartRef = React.useRef<IChartApi | null>(null)
  const lineRef = React.useRef<ISeriesApi<"Line"> | null>(null)
  const baselineRef = React.useRef<ISeriesApi<"Line"> | null>(null)
  const [themeVersion, setThemeVersion] = React.useState(0)

  React.useEffect(() => {
    const el = document.documentElement
    const obs = new MutationObserver(() => setThemeVersion((v) => v + 1))
    obs.observe(el, { attributes: true, attributeFilter: ["class"] })
    return () => obs.disconnect()
  }, [])

  React.useEffect(() => {
    if (!containerRef.current) return
    const palette = getPalette()

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: palette.text,
      },
      grid: {
        vertLines: { color: palette.grid },
        horzLines: { color: palette.grid },
      },
      rightPriceScale: {
        borderColor: palette.border,
      },
      timeScale: {
        borderColor: palette.border,
      },
      crosshair: {
        vertLine: { color: palette.crosshair },
        horzLine: { color: palette.crosshair },
      },
    })

    const line = chart.addSeries(LineSeries, { color: palette.line, lineWidth: 2 })
    const baseline = chart.addSeries(LineSeries, { color: palette.baseline, lineWidth: 1, lineStyle: 2 })

    chartRef.current = chart
    lineRef.current = line
    baselineRef.current = baseline

    const ro = new ResizeObserver(() => {
      if (!containerRef.current) return
      chart.applyOptions({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight })
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      lineRef.current = null
      baselineRef.current = null
    }
  }, [])

  React.useEffect(() => {
    const chart = chartRef.current
    const line = lineRef.current
    const baseline = baselineRef.current
    if (!chart || !line || !baseline) return

    const palette = getPalette()
    chart.applyOptions({
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: palette.text },
      grid: { vertLines: { color: palette.grid }, horzLines: { color: palette.grid } },
      rightPriceScale: { borderColor: palette.border },
      timeScale: { borderColor: palette.border },
      crosshair: { vertLine: { color: palette.crosshair }, horzLine: { color: palette.crosshair } },
    })
    line.applyOptions({ color: palette.line })
    baseline.applyOptions({ color: palette.baseline })
  }, [themeVersion])

  React.useEffect(() => {
    const chart = chartRef.current
    const line = lineRef.current
    const baseline = baselineRef.current
    if (!chart || !line || !baseline) return

    const preds = prediction.predictions
      .slice()
      .sort((a, b) => new Date(a.target_time).getTime() - new Date(b.target_time).getTime())

    const data: LineData[] = preds.map((p) => ({ time: toUtcTs(p.target_time), value: p.pred_close }))
    line.setData(data)

    if (baselineClose != null && data.length) {
      baseline.setData([
        { time: data[0].time, value: baselineClose },
        { time: data[data.length - 1].time, value: baselineClose },
      ])
    } else {
      baseline.setData([])
    }

    if (data.length) {
      chart.timeScale().setVisibleRange({ from: data[0].time, to: data[data.length - 1].time })
    }
  }, [prediction, baselineClose])

  return <div ref={containerRef} className="h-[220px] w-full" />
}

export { PredictionCloseChart }
