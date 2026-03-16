import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import * as React from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock("@/components/candles-chart", () => ({
  CandlesChart: () => <div data-testid="candles-chart" />,
}))

vi.mock("@/components/mode-toggle", () => ({
  ModeToggle: () => <div data-testid="mode-toggle" />,
}))

vi.mock("@/components/prediction-close-chart", () => ({
  PredictionCloseChart: () => <div data-testid="prediction-close-chart" />,
}))

type Candle = {
  open_time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

function makePredictResponse() {
  return {
    status: "success",
    cached: true,
    model_id: "m1",
    as_of_time: "2026-03-15T00:00:00Z",
    generated_at: "2026-03-16T00:00:00Z",
    valid_until: "2026-03-16T23:59:59Z",
    horizon_days: 7,
    predictions: Array.from({ length: 7 }).map((_, i) => ({
      horizon_days: i + 1,
      target_time: `2026-03-${17 + i}T00:00:00Z`,
      pred_open: 1,
      pred_high: 2,
      pred_low: 0.5,
      pred_close: 1.2,
      pred_volume: 10_000,
      pred_components: null,
    })),
  }
}

function makeTrainResponse() {
  return {
    status: "success",
    model_id: "m2",
    trained_at: "2026-03-16T00:00:00Z",
    data_start: "2018-01-01T00:00:00Z",
    data_end: "2026-03-15T00:00:00Z",
    metrics: {
      mae_close_val: 1,
      rmse_close_val: 2,
      best_val_loss: 0.1,
      best_epoch: 3,
      epochs_trained: 5,
      features_used: ["open", "close"],
      metrics_ohlcv_val: {
        MAE_open: 1,
        RMSE_open: 2,
        MAE_high: 1,
        RMSE_high: 2,
        MAE_low: 1,
        RMSE_low: 2,
        MAE_close: 1,
        RMSE_close: 2,
        MAE_volume: 1,
        RMSE_volume: 2,
        invalid_candle_rate_pred: 0,
        invalid_volume_rate_pred: 0,
      },
    },
    training_params: {
      lookback: 60,
      lr: 0.0001,
      weight_decay: 0.0005,
      batch_size: 256,
      max_epochs: 60,
      min_epochs: 10,
      patience: 12,
      min_delta: 0.0001,
      seed: 42,
      holdout_from: "2025-06-01",
      optimizer: "AdamW",
      loss: "SmoothL1Loss",
      in_features: 47,
      feature_cols: ["open", "close"],
      model_hparams: { d_model: 64, n_heads: 4, n_layers: 3, ff_dim: 128, dropout: 0.2, out_dim: 5 },
    },
  }
}

describe("Home loaders", () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it("muestra skeletons durante la carga inicial de candles", async () => {
    const pending = new Promise<Candle[]>(() => {})

    vi.doMock("@/lib/api", async () => {
      const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
      return {
        ...actual,
        getCandles: vi.fn(() => pending),
        getHealthLive: vi.fn(() => Promise.resolve({ status: "ok" })),
        getHealthReady: vi.fn(() => Promise.resolve({ status: "ready" })),
        getLatestModel: vi.fn(() => Promise.resolve(null)),
        predict: vi.fn(() => Promise.resolve(makePredictResponse())),
      }
    })

    const mod = await import("@/app/page")
    render(<mod.HomeView />)

    const kpi = await screen.findByTestId("kpi-close")
    expect(kpi.querySelector("[data-slot='skeleton']")).toBeTruthy()
  })

  it("muestra overlay de entrenamiento con mensajes progresivos", async () => {
    let resolveTrain: (v: unknown) => void = () => {}
    const trainPromise = new Promise((r) => {
      resolveTrain = r
    })

    vi.doMock("@/lib/api", () => ({
      getCandles: vi.fn(() => Promise.resolve([])),
      getHealthLive: vi.fn(() => Promise.resolve({ status: "ok" })),
      getHealthReady: vi.fn(() => Promise.resolve({ status: "ready" })),
      getLatestModel: vi.fn(() => Promise.resolve(null)),
      predict: vi.fn(() => Promise.resolve(makePredictResponse())),
      trainModel: vi.fn(() => trainPromise),
    }))

    const mod = await import("@/app/page")
    render(<mod.HomeView initialTab="train" />)

    const trainBtn = screen.getByRole("button", { name: "Entrenar" })

    vi.useFakeTimers()
    try {
      act(() => {
        fireEvent.click(trainBtn)
      })

      expect(screen.getByTestId("loading-overlay")).toBeInTheDocument()
      expect(screen.getByTestId("loading-message")).toHaveTextContent("Iniciando entrenamiento")

      act(() => {
        vi.advanceTimersByTime(800)
      })
      expect(screen.getByTestId("loading-message")).toHaveTextContent("Procesando datos")

      act(() => {
        vi.advanceTimersByTime(1200)
      })
      expect(screen.getByTestId("loading-message")).toHaveTextContent("Optimizando modelo")

      await act(async () => {
        resolveTrain(makeTrainResponse())
        await Promise.resolve()
      })

      expect(screen.getByText(/model_id:\s*m2/i)).toBeInTheDocument()
      expect(screen.queryByTestId("loading-overlay")).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("muestra spinner/overlay de inferencia al generar predicción", async () => {
    let resolvePred: (v: unknown) => void = () => {}
    const predPromise = new Promise((r) => {
      resolvePred = r
    })

    vi.doMock("@/lib/api", () => ({
      getCandles: vi.fn(() =>
        Promise.resolve([
          {
            open_time: "2026-03-15T00:00:00Z",
            open: 1,
            high: 2,
            low: 0.5,
            close: 1.2,
            volume: 100,
          },
        ]),
      ),
      getHealthLive: vi.fn(() => Promise.resolve({ status: "ok" })),
      getHealthReady: vi.fn(() => Promise.resolve({ status: "ready" })),
      getLatestModel: vi.fn(() => Promise.resolve(null)),
      predict: vi
        .fn()
        .mockResolvedValueOnce(makePredictResponse())
        .mockReturnValueOnce(predPromise),
      trainModel: vi.fn(() => Promise.resolve(makeTrainResponse())),
    }))

    const mod = await import("@/app/page")
    render(<mod.HomeView initialTab="dashboard" />)

    const btn = await screen.findByRole("button", { name: /Actualizar predicción \(7D\)/i })
    await waitFor(() => expect(btn).toBeEnabled())
    act(() => {
      fireEvent.click(btn)
    })

    expect(screen.getByText("Ejecutando inferencia")).toBeInTheDocument()

    await act(async () => {
      resolvePred(makePredictResponse())
      await Promise.resolve()
    })

    expect(screen.queryByText("Ejecutando inferencia")).not.toBeInTheDocument()
  })
})
