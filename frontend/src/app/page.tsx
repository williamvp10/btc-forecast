"use client"

import * as React from "react"
import { RefreshCcwIcon } from "lucide-react"
import { toast } from "sonner"

import { CandlesChart } from "@/components/candles-chart"
import { LoadingOverlay } from "@/components/loading-overlay"
import { ModeToggle } from "@/components/mode-toggle"
import { PredictionCloseChart } from "@/components/prediction-close-chart"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  getCandles,
  getHealthLive,
  getHealthReady,
  getLatestModel,
  predict,
  trainModel,
  type Candle,
  type PredictResponse,
  type TrainResponse,
} from "@/lib/api"
import { formatDateUTC, formatPct, formatPrice, formatVolume } from "@/lib/format"

const SYMBOL = "XBX-USD"
const INTERVAL = "1d"
const DAYS_DEFAULT = 30
const CANDLES_PAGE_SIZE = 100

function asNumber(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null
}

function asString(v: unknown): string | null {
  return typeof v === "string" ? v : null
}

function asRecord(v: unknown): Record<string, unknown> | null {
  if (!v || typeof v !== "object") return null
  return v as Record<string, unknown>
}

function asStringArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x) => typeof x === "string") : []
}

function formatMetric(v: number | null): string {
  if (v == null) return "—"
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 6 }).format(v)
}

type TabKey = "dashboard" | "train"

function HomeView({ initialTab = "dashboard" }: { initialTab?: TabKey }) {
  const [liveOk, setLiveOk] = React.useState<boolean | null>(null)
  const [readyOk, setReadyOk] = React.useState<boolean | null>(null)
  const [candles, setCandles] = React.useState<Candle[]>([])
  const [hasMoreCandles, setHasMoreCandles] = React.useState(true)
  const [loadingMoreCandles, setLoadingMoreCandles] = React.useState(false)
  const [loadMoreCandlesError, setLoadMoreCandlesError] = React.useState<string | null>(null)
  const [prediction, setPrediction] = React.useState<PredictResponse | null>(null)
  const [lastUpdatedAt, setLastUpdatedAt] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [trainLoading, setTrainLoading] = React.useState(false)
  const [predictLoading, setPredictLoading] = React.useState(false)
  const [trainStage, setTrainStage] = React.useState<string | null>(null)
  const [lastTrain, setLastTrain] = React.useState<TrainResponse | null>(null)
  const [loadError, setLoadError] = React.useState<string | null>(null)
  const [trainError, setTrainError] = React.useState<string | null>(null)
  const [predictError, setPredictError] = React.useState<string | null>(null)

  const trainTimersRef = React.useRef<number[]>([])

  React.useEffect(() => {
    return () => {
      trainTimersRef.current.forEach((id) => window.clearTimeout(id))
      trainTimersRef.current = []
    }
  }, [])

  const [trainParams, setTrainParams] = React.useState({
    symbol: SYMBOL,
    interval: INTERVAL,
    feature_set: "full",
    lookback: "60",
    lr: "0.0001",
    weight_decay: "0.0005",
    batch_size: "256",
    max_epochs: "60",
    min_epochs: "10",
    patience: "12",
    min_delta: "0.0001",
    seed: "42",
    holdout_from: "2025-06-01",
  })

  const mergeCandles = React.useCallback((prev: Candle[], next: Candle[]): Candle[] => {
    const byTs = new Map<string, Candle>()
    for (const c of prev) byTs.set(c.open_time, c)
    for (const c of next) byTs.set(c.open_time, c)
    return Array.from(byTs.values()).sort((a, b) => new Date(a.open_time).getTime() - new Date(b.open_time).getTime())
  }, [])

  const loadMoreCandles = React.useCallback(
    async (attempt = 0) => {
      if (loadingMoreCandles || !hasMoreCandles) return
      if (!candles.length) return

      setLoadingMoreCandles(true)
      setLoadMoreCandlesError(null)
      const oldest = candles[0]!.open_time

      try {
        const res = await getCandles({
          symbol: SYMBOL,
          interval: INTERVAL,
          end: oldest,
          limit: CANDLES_PAGE_SIZE,
          order: "desc",
        })

        const merged = mergeCandles(candles, res)
        setCandles(merged)

        if (res.length < CANDLES_PAGE_SIZE || merged[0]?.open_time === oldest) {
          setHasMoreCandles(false)
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Error cargando histórico"
        setLoadMoreCandlesError(msg)
        if (attempt < 2) {
          window.setTimeout(() => void loadMoreCandles(attempt + 1), 1500)
        }
      } finally {
        setLoadingMoreCandles(false)
      }
    },
    [candles, hasMoreCandles, loadingMoreCandles, mergeCandles],
  )

  const loadAll = React.useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    setHasMoreCandles(true)
    setLoadMoreCandlesError(null)
    try {
      const start = new Date(Date.now() - DAYS_DEFAULT * 24 * 60 * 60 * 1000).toISOString()
      const end = new Date().toISOString()
      const [candlesRes, _live, _ready, latestModel] = await Promise.all([
        getCandles({ symbol: SYMBOL, interval: INTERVAL, start, end, limit: 60, order: "desc" }),
        getHealthLive().then(
          () => setLiveOk(true),
          () => setLiveOk(false),
        ),
        getHealthReady().then(
          () => setReadyOk(true),
          () => setReadyOk(false),
        ),
        getLatestModel({ symbol: SYMBOL, interval: INTERVAL, active_only: true }).catch(() => null),
      ])
      setCandles(candlesRes)
      setLastUpdatedAt(new Date().toISOString())
      if (latestModel?.model) {
        setLastTrain({
          status: "success",
          model_id: latestModel.model.model_id,
          trained_at: latestModel.model.trained_at,
          data_start: latestModel.model.data_start,
          data_end: latestModel.model.data_end,
          metrics: latestModel.model.metrics ?? {},
          training_params: latestModel.model.training_params ?? null,
        })
      }

      try {
        setPredictLoading(true)
        setPredictError(null)
        const predRes = await predict({ symbol: SYMBOL, interval: INTERVAL, horizon_days: 7 })
        setPrediction(predRes)
      } catch (e) {
        setPrediction(null)
        const msg = e instanceof Error ? e.message : "Error cargando predicción"
        setPredictError(msg)
        toast.error(msg)
      } finally {
        setPredictLoading(false)
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Error cargando datos"
      setLoadError(msg)
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    void loadAll()
  }, [loadAll])

  const lastCandle = candles.at(-1) ?? null
  const prevCandle = candles.length >= 2 ? candles.at(-2) ?? null : null
  const close = lastCandle?.close ?? null
  const deltaAbs = close != null && prevCandle?.close != null ? close - prevCandle.close : null
  const deltaPct = close != null && prevCandle?.close != null ? (close - prevCandle.close) / prevCandle.close : null

  const predT1 = prediction?.predictions?.length
    ? prediction.predictions.find((p) => p.horizon_days === 1) ?? prediction.predictions[0]
    : null

  const predUpdated =
    !!lastCandle && !!prediction && new Date(prediction.as_of_time).getTime() >= new Date(lastCandle.open_time).getTime()

  const trainMetrics = lastTrain ? asRecord(lastTrain.metrics) : null
  const trainParamsObj = lastTrain ? asRecord(lastTrain.training_params ?? null) : null
  const trainOhlcv = trainMetrics ? asRecord(trainMetrics.metrics_ohlcv_val) : null
  const trainFeatures =
    asStringArray(trainMetrics?.features_used) || asStringArray(trainParamsObj?.feature_cols)

  function startTrainProgress() {
    setTrainStage("Iniciando entrenamiento...")
    trainTimersRef.current.forEach((id) => window.clearTimeout(id))
    trainTimersRef.current = [
      window.setTimeout(() => setTrainStage("Procesando datos..."), 600),
      window.setTimeout(() => setTrainStage("Optimizando modelo..."), 1600),
    ]
  }

  async function handlePredict(horizonDays: number) {
    setPredictLoading(true)
    setPredictError(null)
    try {
      const res = await predict({ symbol: SYMBOL, interval: INTERVAL, horizon_days: horizonDays })
      setPrediction(res)
      toast.success(res.cached ? "Predicción leída desde caché" : "Predicción generada")
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Error generando predicción"
      setPredictError(msg)
      toast.error(msg)
    } finally {
      setPredictLoading(false)
    }
  }

  async function handleTrain() {
    setTrainLoading(true)
    setTrainError(null)
    startTrainProgress()
    try {
      const res = await trainModel({
        symbol: trainParams.symbol,
        interval: trainParams.interval,
        feature_set: trainParams.feature_set,
        lookback: Number(trainParams.lookback),
        lr: Number(trainParams.lr),
        weight_decay: Number(trainParams.weight_decay),
        batch_size: Number(trainParams.batch_size),
        max_epochs: Number(trainParams.max_epochs),
        min_epochs: Number(trainParams.min_epochs),
        patience: Number(trainParams.patience),
        min_delta: Number(trainParams.min_delta),
        seed: Number(trainParams.seed),
        holdout_from: trainParams.holdout_from,
      })
      setLastTrain(res)
      toast.success("Entrenamiento completado")
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Error entrenando modelo"
      setTrainError(msg)
      toast.error(msg)
    } finally {
      setTrainLoading(false)
      setTrainStage(null)
      trainTimersRef.current.forEach((id) => window.clearTimeout(id))
      trainTimersRef.current = []
    }
  }

  const showDashboardSkeleton = loading && candles.length === 0

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <LoadingOverlay open={trainLoading} scope="page" title="Entrenando modelo" message={trainStage ?? "Por favor espera..."} />
      <header className="sticky top-0 z-50 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 flex-col">
            <div className="truncate text-sm font-semibold">BTC Forecast MVP</div>
            <div className="text-xs text-muted-foreground">BTC / 1D (XBX-USD)</div>
          </div>

          <div className="flex items-center gap-2">
            <Badge variant={liveOk ? "success" : "secondary"}>{liveOk ? "Live" : "Live?"}</Badge>
            <Badge variant={readyOk ? "success" : "secondary"}>{readyOk ? "Ready" : "Ready?"}</Badge>
            <div className="hidden text-xs text-muted-foreground sm:block">
              Últ. act: {lastUpdatedAt ? formatDateUTC(lastUpdatedAt) : "—"}
            </div>
            <Button variant="outline" size="icon" onClick={() => void loadAll()} disabled={loading || trainLoading} aria-label="Actualizar">
              {loading ? <Spinner size="sm" /> : <RefreshCcwIcon className="size-4" />}
            </Button>
            <ModeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6">
        <Tabs defaultValue={initialTab}>
          <TabsList>
            <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
            <TabsTrigger value="train">Entrenamiento & Estado</TabsTrigger>
          </TabsList>

          <TabsContent value="dashboard" className="space-y-6">
            {loadError ? (
              <Card>
                <CardHeader className="flex flex-row items-center justify-between gap-2">
                  <CardTitle>Error cargando datos</CardTitle>
                  <Button variant="outline" onClick={() => void loadAll()} disabled={loading || trainLoading}>
                    Reintentar
                  </Button>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">{loadError}</CardContent>
              </Card>
            ) : null}

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Close actual</CardTitle>
                </CardHeader>
                <CardContent className="text-2xl font-semibold" data-testid="kpi-close">
                  {showDashboardSkeleton ? <Skeleton className="h-8 w-32" /> : close != null ? formatPrice(close) : "—"}
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Δ 24h</CardTitle>
                </CardHeader>
                <CardContent className="text-2xl font-semibold">
                  {showDashboardSkeleton ? (
                    <Skeleton className="h-8 w-44" />
                  ) : deltaAbs != null && deltaPct != null ? (
                    `${formatPrice(deltaAbs)} (${formatPct(deltaPct)})`
                  ) : (
                    "—"
                  )}
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Predicción t+1 (close)</CardTitle>
                </CardHeader>
                <CardContent className="text-2xl font-semibold">
                  {predictLoading ? <Skeleton className="h-8 w-32" /> : predT1 ? formatPrice(predT1.pred_close) : "—"}
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Estado predicción</CardTitle>
                </CardHeader>
                <CardContent className="text-2xl font-semibold">
                  {predictLoading ? (
                    <Skeleton className="h-8 w-36" />
                  ) : prediction ? (
                    predUpdated ? "Actualizada" : "Desfasada"
                  ) : (
                    "—"
                  )}
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between gap-2">
                <CardTitle>Mercado + Predicción</CardTitle>
                <div className="flex items-center gap-2">
                  <Button variant="outline" onClick={() => void handlePredict(1)} disabled={predictLoading || trainLoading}>
                    {predictLoading ? <Spinner size="sm" /> : null}
                    Pred t+1
                  </Button>
                  <Button onClick={() => void handlePredict(7)} disabled={predictLoading || trainLoading}>
                    {predictLoading ? <Spinner size="sm" /> : null}
                    Actualizar predicción (7D)
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="relative">
                <LoadingOverlay open={predictLoading} title="Ejecutando inferencia" message="Generando predicción..." />
                {predictError ? (
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-muted px-3 py-2 text-sm">
                    <div className="text-muted-foreground">{predictError}</div>
                    <Button variant="outline" onClick={() => void handlePredict(7)} disabled={predictLoading || trainLoading}>
                      Reintentar
                    </Button>
                  </div>
                ) : null}
                {candles.length ? (
                  <CandlesChart
                    candles={candles}
                    prediction={prediction}
                    hasMore={hasMoreCandles}
                    loadingMore={loadingMoreCandles}
                    loadMoreError={loadMoreCandlesError}
                    onLoadMore={() => void loadMoreCandles()}
                    onRetryLoadMore={() => void loadMoreCandles(0)}
                  />
                ) : showDashboardSkeleton ? (
                  <Skeleton className="h-[420px] w-full" />
                ) : (
                  <div className="h-[420px] w-full rounded-lg border" />
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="train" className="space-y-6">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between gap-2">
                <CardTitle>Entrenar modelo</CardTitle>
                <Button variant="soft" onClick={() => void handleTrain()} disabled={trainLoading}>
                  {trainLoading ? <Spinner size="sm" /> : null}
                  Entrenar
                </Button>
              </CardHeader>
              <CardContent className="grid gap-4">
                {trainError ? (
                  <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-muted px-3 py-2 text-sm">
                    <div className="text-muted-foreground">{trainError}</div>
                    <Button variant="outline" onClick={() => void handleTrain()} disabled={trainLoading}>
                      Reintentar
                    </Button>
                  </div>
                ) : null}
                <div className="grid gap-3 md:grid-cols-3">
                  <div className="grid gap-2">
                    <Label htmlFor="feature_set">feature_set</Label>
                    <Input
                      id="feature_set"
                      value={trainParams.feature_set}
                      disabled={trainLoading}
                      onChange={(e) => setTrainParams((s) => ({ ...s, feature_set: e.target.value }))}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="lookback">lookback</Label>
                    <Input
                      id="lookback"
                      value={trainParams.lookback}
                      disabled={trainLoading}
                      onChange={(e) => setTrainParams((s) => ({ ...s, lookback: e.target.value }))}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="batch_size">batch_size</Label>
                    <Input
                      id="batch_size"
                      value={trainParams.batch_size}
                      disabled={trainLoading}
                      onChange={(e) => setTrainParams((s) => ({ ...s, batch_size: e.target.value }))}
                    />
                  </div>
                </div>

                <div className="grid gap-3 md:grid-cols-3">
                  <div className="grid gap-2">
                    <Label htmlFor="lr">lr</Label>
                    <Input
                      id="lr"
                      value={trainParams.lr}
                      disabled={trainLoading}
                      onChange={(e) => setTrainParams((s) => ({ ...s, lr: e.target.value }))}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="weight_decay">weight_decay</Label>
                    <Input
                      id="weight_decay"
                      value={trainParams.weight_decay}
                      disabled={trainLoading}
                      onChange={(e) => setTrainParams((s) => ({ ...s, weight_decay: e.target.value }))}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="seed">seed</Label>
                    <Input
                      id="seed"
                      value={trainParams.seed}
                      disabled={trainLoading}
                      onChange={(e) => setTrainParams((s) => ({ ...s, seed: e.target.value }))}
                    />
                  </div>
                </div>

                <div className="grid gap-3 md:grid-cols-4">
                  <div className="grid gap-2">
                    <Label htmlFor="max_epochs">max_epochs</Label>
                    <Input
                      id="max_epochs"
                      value={trainParams.max_epochs}
                      disabled={trainLoading}
                      onChange={(e) => setTrainParams((s) => ({ ...s, max_epochs: e.target.value }))}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="min_epochs">min_epochs</Label>
                    <Input
                      id="min_epochs"
                      value={trainParams.min_epochs}
                      disabled={trainLoading}
                      onChange={(e) => setTrainParams((s) => ({ ...s, min_epochs: e.target.value }))}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="patience">patience</Label>
                    <Input
                      id="patience"
                      value={trainParams.patience}
                      disabled={trainLoading}
                      onChange={(e) => setTrainParams((s) => ({ ...s, patience: e.target.value }))}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="min_delta">min_delta</Label>
                    <Input
                      id="min_delta"
                      value={trainParams.min_delta}
                      disabled={trainLoading}
                      onChange={(e) => setTrainParams((s) => ({ ...s, min_delta: e.target.value }))}
                    />
                  </div>
                </div>

                <div className="grid gap-2 md:max-w-sm">
                  <Label htmlFor="holdout_from">holdout_from</Label>
                  <Input
                    id="holdout_from"
                    value={trainParams.holdout_from}
                    disabled={trainLoading}
                    onChange={(e) => setTrainParams((s) => ({ ...s, holdout_from: e.target.value }))}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between gap-2">
                <CardTitle>Último entrenamiento</CardTitle>
                <Button variant="outline" onClick={() => void handlePredict(7)} disabled={!lastTrain}>
                  Generar predicción (7D)
                </Button>
              </CardHeader>
              <CardContent>
                {lastTrain ? (
                  <div className="grid gap-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={lastTrain.status === "success" ? "success" : "destructive"}>
                        {lastTrain.status === "success" ? "OK" : lastTrain.status}
                      </Badge>
                      <div className="text-xs text-muted-foreground">model_id: {lastTrain.model_id}</div>
                    </div>

                    <div className="grid gap-3 md:grid-cols-3">
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm">Fechas</CardTitle>
                        </CardHeader>
                        <CardContent className="grid gap-1 text-sm">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">trained_at</span>
                            <span className="font-medium">{formatDateUTC(lastTrain.trained_at)}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">data_start</span>
                            <span className="font-medium">{formatDateUTC(lastTrain.data_start)}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">data_end</span>
                            <span className="font-medium">{formatDateUTC(lastTrain.data_end)}</span>
                          </div>
                        </CardContent>
                      </Card>

                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm">Métricas (val)</CardTitle>
                        </CardHeader>
                        <CardContent className="grid gap-1 text-sm">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">mae_close</span>
                            <span className="font-medium">{formatMetric(asNumber(trainMetrics?.mae_close_val))}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">rmse_close</span>
                            <span className="font-medium">{formatMetric(asNumber(trainMetrics?.rmse_close_val))}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">best_val_loss</span>
                            <span className="font-medium">{formatMetric(asNumber(trainMetrics?.best_val_loss))}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">val_loss_last</span>
                            <span className="font-medium">{formatMetric(asNumber(trainMetrics?.val_loss_last))}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">train_loss_last</span>
                            <span className="font-medium">{formatMetric(asNumber(trainMetrics?.train_loss_last))}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">epochs</span>
                            <span className="font-medium">
                              {asNumber(trainMetrics?.epochs_trained) ?? "—"} (best: {asNumber(trainMetrics?.best_epoch) ?? "—"})
                            </span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">mse_components</span>
                            <span className="font-medium">{formatMetric(asNumber(trainMetrics?.mse_components_val))}</span>
                          </div>
                        </CardContent>
                      </Card>

                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm">Hiperparámetros</CardTitle>
                        </CardHeader>
                        <CardContent className="grid gap-1 text-sm">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">lookback</span>
                            <span className="font-medium">{asNumber(trainParamsObj?.lookback) ?? "—"}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">lr</span>
                            <span className="font-medium">{formatMetric(asNumber(trainParamsObj?.lr))}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">weight_decay</span>
                            <span className="font-medium">{formatMetric(asNumber(trainParamsObj?.weight_decay))}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">batch_size</span>
                            <span className="font-medium">{asNumber(trainParamsObj?.batch_size) ?? "—"}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">max_epochs</span>
                            <span className="font-medium">{asNumber(trainParamsObj?.max_epochs) ?? "—"}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">min_epochs</span>
                            <span className="font-medium">{asNumber(trainParamsObj?.min_epochs) ?? "—"}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">patience</span>
                            <span className="font-medium">{asNumber(trainParamsObj?.patience) ?? "—"}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">min_delta</span>
                            <span className="font-medium">{formatMetric(asNumber(trainParamsObj?.min_delta))}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">seed</span>
                            <span className="font-medium">{asNumber(trainParamsObj?.seed) ?? "—"}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">holdout_from</span>
                            <span className="font-medium">{asString(trainParamsObj?.holdout_from) ?? "—"}</span>
                          </div>
                        </CardContent>
                      </Card>
                    </div>

                    <div className="grid gap-3 lg:grid-cols-2">
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm">Métricas OHLCV (val)</CardTitle>
                        </CardHeader>
                        <CardContent>
                          {trainOhlcv ? (
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>Métrica</TableHead>
                                  <TableHead className="text-right">MAE</TableHead>
                                  <TableHead className="text-right">RMSE</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {(["open", "high", "low", "close", "volume"] as const).map((k) => (
                                  <TableRow key={k}>
                                    <TableCell className="font-medium">{k}</TableCell>
                                    <TableCell className="text-right">
                                      {formatMetric(asNumber(trainOhlcv[`MAE_${k}`]))}
                                    </TableCell>
                                    <TableCell className="text-right">
                                      {formatMetric(asNumber(trainOhlcv[`RMSE_${k}`]))}
                                    </TableCell>
                                  </TableRow>
                                ))}
                                <TableRow>
                                  <TableCell className="font-medium">invalid_candle_rate</TableCell>
                                  <TableCell className="text-right" colSpan={2}>
                                    {formatMetric(asNumber(trainOhlcv.invalid_candle_rate_pred))}
                                  </TableCell>
                                </TableRow>
                                <TableRow>
                                  <TableCell className="font-medium">invalid_volume_rate</TableCell>
                                  <TableCell className="text-right" colSpan={2}>
                                    {formatMetric(asNumber(trainOhlcv.invalid_volume_rate_pred))}
                                  </TableCell>
                                </TableRow>
                              </TableBody>
                            </Table>
                          ) : (
                            <div className="text-sm text-muted-foreground">No hay métricas OHLCV disponibles.</div>
                          )}
                        </CardContent>
                      </Card>

                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm">Features</CardTitle>
                        </CardHeader>
                        <CardContent className="grid gap-3">
                          <div className="flex flex-wrap gap-1.5">
                            {(trainFeatures.length ? trainFeatures : []).slice(0, 48).map((f) => (
                              <Badge key={f} variant="secondary">
                                #{f}
                              </Badge>
                            ))}
                            {trainFeatures.length > 48 ? (
                              <Badge variant="outline">+{trainFeatures.length - 48} más</Badge>
                            ) : null}
                          </div>
                          <Separator />
                          <div className="grid gap-1 text-sm">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-muted-foreground">optimizer</span>
                              <span className="font-medium">{asString(trainParamsObj?.optimizer) ?? "—"}</span>
                            </div>
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-muted-foreground">loss</span>
                              <span className="font-medium">{asString(trainParamsObj?.loss) ?? "—"}</span>
                            </div>
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-muted-foreground">in_features</span>
                              <span className="font-medium">{asNumber(trainParamsObj?.in_features) ?? "—"}</span>
                            </div>
                            {asRecord(trainParamsObj?.model_hparams) ? (
                              <>
                                <Separator />
                                <div className="text-xs font-medium text-muted-foreground">model_hparams</div>
                                {(["d_model", "n_heads", "n_layers", "ff_dim", "dropout", "out_dim"] as const).map((k) => (
                                  <div key={k} className="flex items-center justify-between gap-2">
                                    <span className="text-muted-foreground">{k}</span>
                                    <span className="font-medium">
                                      {formatMetric(asNumber(asRecord(trainParamsObj?.model_hparams)?.[k]))}
                                    </span>
                                  </div>
                                ))}
                              </>
                            ) : null}
                          </div>
                        </CardContent>
                      </Card>
                    </div>
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground">Todavía no hay entrenamiento ejecutado.</div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Última predicción</CardTitle>
              </CardHeader>
              <CardContent>
                {prediction ? (
                  <div className="grid gap-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={prediction.status === "success" ? "success" : "default"}>{prediction.status}</Badge>
                      <Badge variant={prediction.cached ? "secondary" : "outline"}>{prediction.cached ? "cached" : "fresh"}</Badge>
                      <div className="text-xs text-muted-foreground">model_id: {prediction.model_id}</div>
                    </div>

                    <div className="grid gap-3 md:grid-cols-3">
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm">Corte y validez</CardTitle>
                        </CardHeader>
                        <CardContent className="grid gap-1 text-sm">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">as_of</span>
                            <span className="font-medium">{formatDateUTC(prediction.as_of_time)}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">generated</span>
                            <span className="font-medium">{formatDateUTC(prediction.generated_at)}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">valid_until</span>
                            <span className="font-medium">{formatDateUTC(prediction.valid_until)}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">horizon</span>
                            <span className="font-medium">{prediction.horizon_days}d</span>
                          </div>
                        </CardContent>
                      </Card>

                      <Card className="md:col-span-2">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm">Predicción (close)</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <PredictionCloseChart prediction={prediction} baselineClose={close} />
                        </CardContent>
                      </Card>
                    </div>

                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">Tabla (t+1..t+7)</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>t+</TableHead>
                              <TableHead>fecha</TableHead>
                              <TableHead className="text-right">open</TableHead>
                              <TableHead className="text-right">high</TableHead>
                              <TableHead className="text-right">low</TableHead>
                              <TableHead className="text-right">close</TableHead>
                              <TableHead className="text-right">volume</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {prediction.predictions
                              .slice()
                              .sort((a, b) => a.horizon_days - b.horizon_days)
                              .map((p) => (
                                <TableRow key={p.horizon_days}>
                                  <TableCell className="font-medium">{p.horizon_days}</TableCell>
                                  <TableCell>{formatDateUTC(p.target_time)}</TableCell>
                                  <TableCell className="text-right">{formatPrice(p.pred_open)}</TableCell>
                                  <TableCell className="text-right">{formatPrice(p.pred_high)}</TableCell>
                                  <TableCell className="text-right">{formatPrice(p.pred_low)}</TableCell>
                                  <TableCell className="text-right">{formatPrice(p.pred_close)}</TableCell>
                                  <TableCell className="text-right">{formatVolume(p.pred_volume)}</TableCell>
                                </TableRow>
                              ))}
                          </TableBody>
                        </Table>
                      </CardContent>
                    </Card>
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground">Todavía no hay predicción generada.</div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>

      <footer className="border-t">
        <div className="mx-auto max-w-6xl px-4 py-6 text-xs text-muted-foreground">
          Proyección semanal solo para visualización; no constituye recomendación financiera.
        </div>
      </footer>
    </div>
  )
}

export { HomeView }

export default function Home() {
  return <HomeView />
}
