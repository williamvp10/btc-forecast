type ProblemDetails = {
  title?: string
  detail?: string
  errors?: unknown
}

const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_URL ?? "").replace(/\/+$/, "")

function withBase(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path
  const normalizedPath = path.startsWith("/") ? path : `/${path}`
  if (!BACKEND_URL) return normalizedPath
  return `${BACKEND_URL}${normalizedPath}`
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(withBase(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  })

  if (res.ok) return (await res.json()) as T

  let body: unknown = null
  try {
    body = await res.json()
  } catch {}

  const prob = body as ProblemDetails
  const msg =
    (prob?.title && prob?.detail ? `${prob.title}: ${prob.detail}` : prob?.detail || prob?.title) ||
    `${res.status} ${res.statusText}`

  throw new Error(msg)
}

export type Candle = {
  open_time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export type PredictionItem = {
  horizon_days: number
  target_time: string
  pred_open: number
  pred_high: number
  pred_low: number
  pred_close: number
  pred_volume: number
  pred_components?: Record<string, unknown> | null
}

export type PredictRequest = {
  symbol: string
  interval?: string
  horizon_days?: number
}

export type PredictResponse = {
  status: string
  cached: boolean
  model_id: string
  as_of_time: string
  generated_at: string
  valid_until: string
  horizon_days: number
  predictions: PredictionItem[]
}

export type TrainRequest = {
  symbol: string
  interval?: string
  feature_set?: string
  lookback?: number
  lr?: number
  weight_decay?: number
  batch_size?: number
  max_epochs?: number
  min_epochs?: number
  patience?: number
  min_delta?: number
  seed?: number
  holdout_from?: string
}

export type TrainResponse = {
  status: string
  model_id: string
  trained_at: string
  data_start: string
  data_end: string
  metrics: Record<string, unknown>
  training_params?: Record<string, unknown> | null
}

export type LatestModelItem = {
  model_id: string
  symbol: string
  interval: string
  name: string
  trained_at: string
  data_start: string
  data_end: string
  target: string
  feature_set: string
  window_size_days: number
  horizon_days: number
  is_active: boolean
  metrics: Record<string, unknown>
  training_params?: Record<string, unknown> | null
}

export type LatestModelResponse = {
  status: string
  model: LatestModelItem
}

export async function getHealthLive(): Promise<unknown> {
  return fetchJson("/health/live", { cache: "no-store" })
}

export async function getHealthReady(): Promise<unknown> {
  return fetchJson("/health/ready", { cache: "no-store" })
}

export async function getCandles(params: {
  symbol: string
  interval?: string
  start?: string
  end?: string
  limit?: number
  order?: "asc" | "desc"
}): Promise<Candle[]> {
  const qs = new URLSearchParams()
  qs.set("symbol", params.symbol)
  if (params.interval) qs.set("interval", params.interval)
  if (params.start) qs.set("start", params.start)
  if (params.end) qs.set("end", params.end)
  if (params.limit) qs.set("limit", String(params.limit))
  if (params.order) qs.set("order", params.order)

  return fetchJson(`/api/v1/market/candles?${qs.toString()}`, { cache: "no-store" })
}

export async function trainModel(req: TrainRequest): Promise<TrainResponse> {
  return fetchJson("/api/v1/train", {
    method: "POST",
    body: JSON.stringify(req),
  })
}

export async function predict(req: PredictRequest): Promise<PredictResponse> {
  return fetchJson("/api/v1/predict", {
    method: "POST",
    body: JSON.stringify(req),
  })
}

export async function getLatestModel(params: {
  symbol: string
  interval?: string
  active_only?: boolean
}): Promise<LatestModelResponse> {
  const qs = new URLSearchParams()
  qs.set("symbol", params.symbol)
  if (params.interval) qs.set("interval", params.interval)
  if (typeof params.active_only === "boolean") qs.set("active_only", String(params.active_only))

  return fetchJson(`/api/v1/model/latest?${qs.toString()}`, { cache: "no-store" })
}
