"use client"

import * as React from "react"
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type UTCTimestamp,
} from "lightweight-charts"

import type { Candle, PredictResponse } from "@/lib/api"
import { Spinner } from "@/components/ui/spinner"
import { Button } from "@/components/ui/button"

type Props = {
  candles: Candle[]
  prediction?: PredictResponse | null
  hasMore?: boolean
  loadingMore?: boolean
  loadMoreError?: string | null
  onLoadMore?: () => void
  onRetryLoadMore?: () => void
}

function toUtcTs(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp
}

function formatCompact(n: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(n)
}

function formatInt(n: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(n)
}

function formatDate(ts: UTCTimestamp): string {
  const d = new Date(ts * 1000)
  return d.toISOString().slice(0, 10)
}

function getPalette() {
  const isDark = document.documentElement.classList.contains("dark")

  if (isDark) {
    return {
      text: "#fafafa",
      grid: "#27272a",
      border: "#27272a",
      crosshair: "#71717a",
      volume: "rgba(161,161,170,0.45)",
      volumePred: "rgba(161,161,170,0.22)",
    }
  }

  return {
    text: "#0a0a0a",
    grid: "#e5e7eb",
    border: "#e5e7eb",
    crosshair: "#a1a1aa",
    volume: "rgba(100,116,139,0.45)",
    volumePred: "rgba(100,116,139,0.22)",
  }
}

function CandlesChart({ candles, prediction, hasMore = false, loadingMore = false, loadMoreError = null, onLoadMore, onRetryLoadMore }: Props) {
  const containerRef = React.useRef<HTMLDivElement | null>(null)
  const chartRef = React.useRef<IChartApi | null>(null)
  const candleSeriesRef = React.useRef<ISeriesApi<"Candlestick"> | null>(null)
  const volSeriesRef = React.useRef<ISeriesApi<"Histogram"> | null>(null)
  const predSeriesRef = React.useRef<ISeriesApi<"Candlestick"> | null>(null)
  const projSeriesRef = React.useRef<ISeriesApi<"Candlestick"> | null>(null)
  const prevFirstRef = React.useRef<UTCTimestamp | null>(null)
  const didFitRef = React.useRef(false)
  const hasMoreRef = React.useRef(hasMore)
  const loadingMoreRef = React.useRef(loadingMore)
  const onLoadMoreRef = React.useRef<(() => void) | undefined>(onLoadMore)
  const rafRef = React.useRef<number | null>(null)
  const [tooltip, setTooltip] = React.useState<{
    open: boolean
    left: number
    top: number
    label: string
    date: string
    o: number
    h: number
    l: number
    c: number
    vol: number | null
  }>({ open: false, left: 0, top: 0, label: "", date: "", o: 0, h: 0, l: 0, c: 0, vol: null })
  const [themeVersion, setThemeVersion] = React.useState(0)

  React.useEffect(() => {
    hasMoreRef.current = hasMore
    loadingMoreRef.current = loadingMore
    onLoadMoreRef.current = onLoadMore
  }, [hasMore, loadingMore, onLoadMore])

  React.useEffect(() => {
    return () => {
      if (rafRef.current != null) window.cancelAnimationFrame(rafRef.current)
    }
  }, [])

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
        scaleMargins: { top: 0.1, bottom: 0.28 },
      },
      timeScale: {
        borderColor: palette.border,
      },
      crosshair: {
        vertLine: { color: palette.crosshair },
        horzLine: { color: palette.crosshair },
      },
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#16a34a",
      downColor: "#dc2626",
      borderUpColor: "#16a34a",
      borderDownColor: "#dc2626",
      wickUpColor: "#16a34a",
      wickDownColor: "#dc2626",
    })

    const volSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
      color: palette.volume,
      base: 0,
    })

    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.78, bottom: 0 },
      visible: false,
      borderVisible: false,
    })

    const predSeries = chart.addSeries(CandlestickSeries, {
      upColor: "rgba(34,197,94,0.6)",
      downColor: "rgba(239,68,68,0.6)",
      borderUpColor: "rgba(34,197,94,1.0)",
      borderDownColor: "rgba(239,68,68,1.0)",
      wickUpColor: "rgba(34,197,94,0.9)",
      wickDownColor: "rgba(239,68,68,0.9)",
    })

    const projSeries = chart.addSeries(CandlestickSeries, {
      upColor: "rgba(34,197,94,0.35)",
      downColor: "rgba(239,68,68,0.35)",
      borderUpColor: "rgba(34,197,94,0.6)",
      borderDownColor: "rgba(239,68,68,0.6)",
      wickUpColor: "rgba(34,197,94,0.5)",
      wickDownColor: "rgba(239,68,68,0.5)",
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volSeriesRef.current = volSeries
    predSeriesRef.current = predSeries
    projSeriesRef.current = projSeries

    const ro = new ResizeObserver(() => {
      if (!containerRef.current) return
      chart.applyOptions({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight })
    })
    ro.observe(containerRef.current)

    const ts = chart.timeScale()
    const onRange = (range: { from: number; to: number } | null) => {
      if (!range) return
      if (!hasMoreRef.current || loadingMoreRef.current) return
      const load = onLoadMoreRef.current
      if (!load) return
      if (range.from < 5) load()
    }
    ts.subscribeVisibleLogicalRangeChange(onRange)

    const onCrosshair = (param: { point?: { x: number; y: number }; time?: UTCTimestamp; seriesData?: Map<unknown, unknown> }) => {
      if (!param.point || param.time == null || !param.seriesData) {
        if (rafRef.current != null) window.cancelAnimationFrame(rafRef.current)
        rafRef.current = window.requestAnimationFrame(() => setTooltip((s) => ({ ...s, open: false })))
        return
      }

      const candleSeries = candleSeriesRef.current
      const predSeries = predSeriesRef.current
      const projSeries = projSeriesRef.current
      const volSeries = volSeriesRef.current
      if (!candleSeries || !predSeries || !projSeries || !volSeries) return

      const pick = (s: unknown) => param.seriesData!.get(s as never) as CandlestickData | HistogramData | undefined

      const pred = pick(predSeries)
      const proj = pick(projSeries)
      const real = pick(candleSeries)
      const vol = pick(volSeries) as HistogramData | undefined

      const candle = (pred && "open" in pred ? pred : proj && "open" in proj ? proj : real && "open" in real ? real : null) as
        | CandlestickData
        | null

      if (!candle) {
        if (rafRef.current != null) window.cancelAnimationFrame(rafRef.current)
        rafRef.current = window.requestAnimationFrame(() => setTooltip((s) => ({ ...s, open: false })))
        return
      }

      const label = pred && "open" in pred ? "Predicción t+1" : proj && "open" in proj ? "Predicción" : "Mercado"
      const { x, y } = param.point
      const boxW = 190
      const boxH = 108
      const pad = 10
      const container = containerRef.current
      if (!container) return
      const w = container.clientWidth
      const h = container.clientHeight

      const left = Math.max(pad, Math.min(x + pad, w - boxW - pad))
      const top = Math.max(pad, Math.min(y - boxH - pad, h - boxH - pad))

      if (rafRef.current != null) window.cancelAnimationFrame(rafRef.current)
      rafRef.current = window.requestAnimationFrame(() => {
        setTooltip({
          open: true,
          left,
          top,
          label,
          date: formatDate(param.time!),
          o: candle.open,
          h: candle.high,
          l: candle.low,
          c: candle.close,
          vol: vol?.value != null ? Number(vol.value) : null,
        })
      })
    }
    chart.subscribeCrosshairMove(onCrosshair as never)

    return () => {
      ts.unsubscribeVisibleLogicalRangeChange(onRange)
      chart.unsubscribeCrosshairMove(onCrosshair as never)
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      volSeriesRef.current = null
      predSeriesRef.current = null
      projSeriesRef.current = null
    }
  }, [])

  React.useEffect(() => {
    const chart = chartRef.current
    const volSeries = volSeriesRef.current
    if (!chart || !volSeries) return

    const palette = getPalette()
    chart.applyOptions({
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
        scaleMargins: { top: 0.1, bottom: 0.28 },
      },
      timeScale: {
        borderColor: palette.border,
      },
      crosshair: {
        vertLine: { color: palette.crosshair },
        horzLine: { color: palette.crosshair },
      },
    })
    volSeries.applyOptions({ color: palette.volume })
    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.78, bottom: 0 },
      visible: false,
      borderVisible: false,
    })
  }, [themeVersion])

  React.useEffect(() => {
    const chart = chartRef.current
    const candleSeries = candleSeriesRef.current
    const volSeries = volSeriesRef.current
    const predSeries = predSeriesRef.current
    const projSeries = projSeriesRef.current
    if (!chart) return
    if (!candleSeries || !volSeries || !predSeries || !projSeries) return

    const palette = getPalette()
    const prevFirst = prevFirstRef.current
    const rangeBefore = chart.timeScale().getVisibleRange()
    const candleData: CandlestickData[] = candles.map((c) => ({
      time: toUtcTs(c.open_time),
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }))

    const volData: HistogramData[] = candles.map((c) => ({
      time: toUtcTs(c.open_time),
      value: c.volume,
      color: palette.volume,
    }))

    const lastReal = candles.at(-1)
    const lastRealTs = lastReal ? toUtcTs(lastReal.open_time) : null
    const preds = prediction?.predictions?.length ? prediction.predictions : []
    const predT1 = preds.length ? preds.find((p) => p.horizon_days === 1) ?? preds[0] : null
    const volPred: HistogramData[] = preds
      .filter((p) => (!lastRealTs ? true : toUtcTs(p.target_time) > lastRealTs))
      .map((p) => ({
        time: toUtcTs(p.target_time),
        value: p.pred_volume,
        color: palette.volumePred,
      }))
    const proj = preds
      .filter((p) => p.horizon_days >= 2)
      .filter((p) => (!lastRealTs ? true : toUtcTs(p.target_time) > lastRealTs))
      .map((p) => ({
        time: toUtcTs(p.target_time),
        open: p.pred_open,
        high: p.pred_high,
        low: p.pred_low,
        close: p.pred_close,
      }))

    candleSeries.setData(candleData)
    volSeries.setData([...volData, ...volPred])
    const firstNow = candleData.length ? candleData[0].time : null
    const isPrepend = prevFirst != null && firstNow != null && firstNow < prevFirst
    prevFirstRef.current = firstNow

    if (predT1 && (!lastRealTs || toUtcTs(predT1.target_time) > lastRealTs)) {
      predSeries.setData([
        {
          time: toUtcTs(predT1.target_time),
          open: predT1.pred_open,
          high: predT1.pred_high,
          low: predT1.pred_low,
          close: predT1.pred_close,
        },
      ])
    } else {
      predSeries.setData([])
    }

    projSeries.setData(proj)

    if (!didFitRef.current && candleData.length) {
      chart.timeScale().fitContent()
      didFitRef.current = true
    } else if (isPrepend && rangeBefore) {
      chart.timeScale().setVisibleRange(rangeBefore)
    }
  }, [candles, prediction, themeVersion])

  return (
    <div className="relative h-[420px] w-full">
      <div ref={containerRef} className="absolute inset-0" />
      {tooltip.open ? (
        <div
          className="pointer-events-none absolute z-30 w-[190px] rounded-xl border bg-background/90 p-2 shadow-sm backdrop-blur"
          style={{ left: tooltip.left, top: tooltip.top }}
          role="status"
          aria-live="polite"
        >
          <div className="grid gap-1">
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs font-semibold">{tooltip.label}</div>
              <div className="text-[11px] text-muted-foreground">{tooltip.date}</div>
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">O</span>
                <span className="font-medium">{formatCompact(tooltip.o)}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">H</span>
                <span className="font-medium">{formatCompact(tooltip.h)}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">L</span>
                <span className="font-medium">{formatCompact(tooltip.l)}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">C</span>
                <span className="font-medium">{formatCompact(tooltip.c)}</span>
              </div>
              <div className="col-span-2 flex items-center justify-between gap-2">
                <span className="text-muted-foreground">Vol</span>
                <span className="font-medium">{tooltip.vol != null ? formatInt(tooltip.vol) : "—"}</span>
              </div>
            </div>
          </div>
        </div>
      ) : null}
      {loadingMore ? (
        <div className="absolute left-3 top-3 z-20 inline-flex items-center gap-2 rounded-lg border bg-background/80 px-2 py-1 text-xs backdrop-blur">
          <Spinner size="sm" />
          <span>Cargando histórico...</span>
        </div>
      ) : null}
      {loadMoreError ? (
        <div className="absolute left-3 top-3 z-20 inline-flex items-center gap-2 rounded-lg border bg-background/90 px-2 py-1 text-xs backdrop-blur">
          <span className="text-muted-foreground">{loadMoreError}</span>
          <Button size="xs" variant="outline" onClick={onRetryLoadMore} disabled={!onRetryLoadMore}>
            Reintentar
          </Button>
        </div>
      ) : null}
    </div>
  )
}

export { CandlesChart }
