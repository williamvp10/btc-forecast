import hashlib
import os
import random
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import torch
from sqlalchemy.orm import Session
from torch.utils.data import DataLoader, TensorDataset

from app.db.models.metadata import Market
from app.db.models.ml import ModelArtifact
from app.db.models.timeseries import Candle, Feature
from app.services.ml.transformer import TransformerEncoderRegressor


FULL_FEATURE_COLS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "log_close",
    "log_return",
    "log_volume",
    "rsi_14",
    "sma_8",
    "ema_8",
    "sma_20",
    "ema_20",
    "sma_100",
    "ema_100",
    "volatility_7",
    "volatility_30",
    "buying_pressure",
    "candle_range",
    "candle_body",
    "upper_wick",
    "lower_wick",
    "log_ret_lag_1",
    "log_ret_lag_2",
    "log_ret_lag_3",
    "log_ret_lag_4",
    "log_ret_lag_5",
    "log_ret_lag_6",
    "log_ret_lag_7",
    "sin_day",
    "cos_day",
    "sin_month",
    "cos_month",
    "sp500",
    "log_ret_sp500",
    "vol_7d_sp500",
    "dxy",
    "log_ret_dxy",
    "vol_7d_dxy",
    "vix",
    "log_ret_vix",
    "vol_7d_vix",
    "gold",
    "log_ret_gold",
    "vol_7d_gold",
    "fgi",
    "fgi_norm",
]


def _compute_structured_targets(candles: pd.DataFrame) -> pd.DataFrame:
    df = candles.copy()
    df = df.sort_values("timestamp").reset_index(drop=True)

    close_t = df["close"].shift(0)
    open_tp1 = df["open"].shift(-1)
    high_tp1 = df["high"].shift(-1)
    low_tp1 = df["low"].shift(-1)
    close_tp1 = df["close"].shift(-1)
    vol_tp1 = df["volume"].shift(-1)

    gap_open = np.log(open_tp1 / (close_t + 1e-12))
    logret_close = np.log(close_tp1 / (close_t + 1e-12))

    max_oc = np.maximum(open_tp1, close_tp1)
    min_oc = np.minimum(open_tp1, close_tp1)

    high_excess_raw = np.maximum(high_tp1 - max_oc, 0.0)
    low_excess_raw = np.maximum(min_oc - low_tp1, 0.0)

    high_excess = np.log1p(high_excess_raw)
    low_excess = np.log1p(low_excess_raw)

    logvol = np.log1p(np.maximum(vol_tp1, 0.0))

    out = pd.DataFrame(
        {
            "timestamp": df["timestamp"],
            "gap_open": gap_open,
            "logret_close": logret_close,
            "high_excess": high_excess,
            "low_excess": low_excess,
            "logvol": logvol,
            "y_true_open_t1": open_tp1,
            "y_true_high_t1": high_tp1,
            "y_true_low_t1": low_tp1,
            "y_true_close_t1": close_tp1,
            "y_true_volume_t1": vol_tp1,
        }
    )
    return out


def _reconstruct_levels(close_t: float, comps: np.ndarray) -> dict:
    gap_open, logret_close, high_excess, low_excess, logvol = comps.tolist()
    gap_open = float(np.clip(gap_open, -20.0, 20.0))
    logret_close = float(np.clip(logret_close, -20.0, 20.0))
    high_excess = float(np.clip(high_excess, -20.0, 20.0))
    low_excess = float(np.clip(low_excess, -20.0, 20.0))
    logvol = float(np.clip(logvol, -20.0, 20.0))
    open_tp1 = float(close_t * np.exp(gap_open))
    close_tp1 = float(close_t * np.exp(logret_close))
    high_tp1 = float(max(open_tp1, close_tp1) + np.expm1(high_excess))
    low_tp1 = float(min(open_tp1, close_tp1) - np.expm1(low_excess))
    volume_tp1 = float(max(np.expm1(logvol), 0.0))
    return {"open": open_tp1, "high": high_tp1, "low": low_tp1, "close": close_tp1, "volume": volume_tp1}


def _reconstruct_ohlcv_batch(close_t: np.ndarray, comps: np.ndarray) -> np.ndarray:
    close_t = np.asarray(close_t, dtype=float).reshape(-1)
    comps = np.asarray(comps, dtype=float)
    if comps.ndim != 2 or comps.shape[1] != 5:
        raise ValueError("Expected comps shape [n, 5]")

    gap_open = np.clip(comps[:, 0], -20.0, 20.0)
    logret_close = np.clip(comps[:, 1], -20.0, 20.0)
    high_excess = np.clip(comps[:, 2], -20.0, 20.0)
    low_excess = np.clip(comps[:, 3], -20.0, 20.0)
    logvol = np.clip(comps[:, 4], -20.0, 20.0)

    pred_open = close_t * np.exp(gap_open)
    pred_close = close_t * np.exp(logret_close)
    body_max = np.maximum(pred_open, pred_close)
    body_min = np.minimum(pred_open, pred_close)
    pred_high = body_max + np.expm1(high_excess)
    pred_low = body_min - np.expm1(low_excess)
    pred_vol = np.maximum(np.expm1(logvol), 0.0)

    return np.column_stack([pred_open, pred_high, pred_low, pred_close, pred_vol]).astype(float)


def _mae(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float))))


def _rmse(a: np.ndarray, b: np.ndarray) -> float:
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    return float(np.sqrt(np.mean(d * d)))


def _invalid_candle_rate(open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray) -> float:
    open_ = np.asarray(open_, dtype=float)
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    m1 = high < np.maximum(open_, close)
    m2 = low > np.minimum(open_, close)
    m3 = low > high
    invalid = m1 | m2 | m3
    return float(np.mean(invalid))


def _invalid_volume_rate(volume: np.ndarray) -> float:
    volume = np.asarray(volume, dtype=float)
    return float(np.mean(volume < 0))


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def train_model(
    db: Session,
    *,
    symbol: str = "XBX-USD",
    interval: str = "1d",
    feature_set: str = "full",
    lookback: int = 60,
    lr: float = 1e-4,
    weight_decay: float = 5e-4,
    batch_size: int = 256,
    max_epochs: int = 60,
    min_epochs: int = 10,
    patience: int = 12,
    min_delta: float = 1e-4,
    seed: int = 42,
    holdout_from: str = "2025-06-01",
) -> ModelArtifact:
    m = db.query(Market).filter(Market.symbol == symbol).first()
    if not m:
        raise ValueError("Market not found")

    feats = (
        db.query(Feature)
        .filter(Feature.market_id == m.id, Feature.interval == interval, Feature.feature_set == feature_set)
        .order_by(Feature.open_time.asc())
        .all()
    )
    if len(feats) < lookback + 2:
        raise ValueError("Not enough feature rows to train")

    candles = (
        db.query(Candle)
        .filter(Candle.market_id == m.id, Candle.interval == interval)
        .order_by(Candle.open_time.asc())
        .all()
    )
    candles_df = pd.DataFrame(
        [{"timestamp": c.open_time, "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume} for c in candles]
    )
    candles_df["timestamp"] = pd.to_datetime(candles_df["timestamp"], utc=True)
    targets_df = _compute_structured_targets(candles_df)

    feat_df = pd.DataFrame(
        [{"timestamp": f.open_time, **(f.values or {})} for f in feats]
    )
    feat_df["timestamp"] = pd.to_datetime(feat_df["timestamp"], utc=True)
    feat_df = feat_df.sort_values("timestamp").reset_index(drop=True)
    merged = feat_df.merge(targets_df, on="timestamp", how="inner")
    merged = merged.dropna(subset=FULL_FEATURE_COLS + ["gap_open", "logret_close", "high_excess", "low_excess", "logvol"]).reset_index(drop=True)

    X = merged[FULL_FEATURE_COLS].astype(float).to_numpy()
    y = merged[["gap_open", "logret_close", "high_excess", "low_excess", "logvol"]].astype(float).to_numpy()
    ts = merged["timestamp"].to_list()

    x_mean = np.nanmean(X, axis=0)
    x_std = np.nanstd(X, axis=0)
    x_std = np.where(x_std < 1e-12, 1.0, x_std)
    Xs = (X - x_mean) / x_std

    y_mean = np.nanmean(y, axis=0)
    y_std = np.nanstd(y, axis=0)
    y_std = np.where(y_std < 1e-12, 1.0, y_std)
    ys = (y - y_mean) / y_std

    n = len(merged) - 1
    X_seq = []
    y_seq = []
    close_t_seq = []
    y_true_ohlcv_seq = []
    ts_target = []
    for i in range(lookback - 1, n):
        start = i - (lookback - 1)
        end = i + 1
        X_seq.append(Xs[start:end])
        y_seq.append(ys[i])
        close_t_seq.append(float(merged.loc[i, "close"]))
        y_true_ohlcv_seq.append(
            [
                float(merged.loc[i, "y_true_open_t1"]),
                float(merged.loc[i, "y_true_high_t1"]),
                float(merged.loc[i, "y_true_low_t1"]),
                float(merged.loc[i, "y_true_close_t1"]),
                float(merged.loc[i, "y_true_volume_t1"]),
            ]
        )
        ts_target.append(ts[i])

    X_seq = np.stack(X_seq, axis=0)
    y_seq = np.stack(y_seq, axis=0)
    y_true_ohlcv_seq = np.asarray(y_true_ohlcv_seq, dtype=float)

    holdout_ts = pd.to_datetime(holdout_from, utc=True, errors="coerce")
    ts_target_idx = pd.to_datetime(pd.Series(ts_target), utc=True)
    val_mask = ts_target_idx >= holdout_ts if pd.notna(holdout_ts) else pd.Series([False] * len(ts_target_idx))
    train_mask = ~val_mask
    if int(val_mask.sum()) < 10:
        split = int(len(X_seq) * 0.85)
        train_mask = pd.Series([True] * split + [False] * (len(X_seq) - split))
        val_mask = ~train_mask

    X_train = X_seq[train_mask.to_numpy()]
    y_train = y_seq[train_mask.to_numpy()]
    X_val = X_seq[val_mask.to_numpy()]
    y_val = y_seq[val_mask.to_numpy()]
    close_val = list(np.asarray(close_t_seq, dtype=float)[val_mask.to_numpy()])
    y_true_ohlcv_val = y_true_ohlcv_seq[val_mask.to_numpy()]

    random.seed(int(seed))
    np.random.seed(int(seed))
    torch.manual_seed(int(seed))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(seed))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = TransformerEncoderRegressor(in_features=int(X_seq.shape[2])).to(device)

    criterion = torch.nn.SmoothL1Loss()
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(lr),
        weight_decay=float(weight_decay),
        betas=(0.9, 0.98),
        eps=1e-9,
    )
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer,
        mode="min",
        factor=0.5,
        patience=max(1, int(patience) // 3),
    )

    train_ds = TensorDataset(torch.tensor(X_train, dtype=torch.float32), torch.tensor(y_train, dtype=torch.float32))
    val_ds = TensorDataset(torch.tensor(X_val, dtype=torch.float32), torch.tensor(y_val, dtype=torch.float32))
    train_loader = DataLoader(train_ds, batch_size=int(batch_size), shuffle=True, drop_last=False)
    val_loader = DataLoader(val_ds, batch_size=int(batch_size), shuffle=False, drop_last=False)

    history = {"train_loss": [], "val_loss": [], "lr": []}
    best_val = float("inf")
    best_state = None
    bad_epochs = 0

    for epoch in range(1, int(max_epochs) + 1):
        model.train()
        train_losses = []
        for xb, yb in train_loader:
            xb = xb.to(device)
            yb = yb.to(device)
            pred = model(xb)
            loss = criterion(pred, yb)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_losses.append(float(loss.detach().cpu().item()))

        model.eval()
        val_losses = []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb = xb.to(device)
                yb = yb.to(device)
                pred = model(xb)
                loss = criterion(pred, yb)
                val_losses.append(float(loss.detach().cpu().item()))

        train_loss = float(np.mean(train_losses)) if train_losses else float("nan")
        val_loss = float(np.mean(val_losses)) if val_losses else float("nan")
        lr_now = float(optimizer.param_groups[0]["lr"])
        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["lr"].append(lr_now)

        improved = (best_val - val_loss) > float(min_delta)
        if improved:
            best_val = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            bad_epochs = 0
        else:
            bad_epochs += 1

        scheduler.step(val_loss)

        if epoch >= int(min_epochs) and bad_epochs >= int(patience):
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    best_epoch = int(np.argmin(np.asarray(history["val_loss"], dtype=float)) + 1) if history["val_loss"] else None

    model.eval()
    with torch.no_grad():
        pred_val_s = []
        for xb, _ in val_loader:
            xb = xb.to(device)
            pred_val_s.append(model(xb).detach().cpu().numpy())
        pred_val_s = np.concatenate(pred_val_s, axis=0) if pred_val_s else np.zeros((0, 5), dtype=np.float32)
    pred_val = (pred_val_s * y_std) + y_mean
    mse_val = float(np.mean((pred_val_s - y_val) ** 2)) if len(y_val) else float("nan")

    mae_close = float("nan")
    rmse_close = float("nan")
    metrics_ohlcv: dict[str, float] = {}
    if len(pred_val):
        closes = []
        closes_hat = []
        y_val_raw = (y_val * y_std) + y_mean
        for close_t, comps_true, comps_hat in zip(close_val, y_val_raw, pred_val):
            closes.append(_reconstruct_levels(close_t, comps_true)["close"])
            closes_hat.append(_reconstruct_levels(close_t, comps_hat)["close"])
        mae_close = float(np.mean(np.abs(np.array(closes_hat) - np.array(closes))))
        rmse_close = float(np.sqrt(np.mean((np.array(closes_hat) - np.array(closes)) ** 2)))

        pred_ohlcv = _reconstruct_ohlcv_batch(np.asarray(close_val, dtype=float), np.asarray(pred_val, dtype=float))
        true_ohlcv = np.asarray(y_true_ohlcv_val, dtype=float)
        metrics_ohlcv = {
            "MAE_open": _mae(true_ohlcv[:, 0], pred_ohlcv[:, 0]),
            "RMSE_open": _rmse(true_ohlcv[:, 0], pred_ohlcv[:, 0]),
            "MAE_high": _mae(true_ohlcv[:, 1], pred_ohlcv[:, 1]),
            "RMSE_high": _rmse(true_ohlcv[:, 1], pred_ohlcv[:, 1]),
            "MAE_low": _mae(true_ohlcv[:, 2], pred_ohlcv[:, 2]),
            "RMSE_low": _rmse(true_ohlcv[:, 2], pred_ohlcv[:, 2]),
            "MAE_close": _mae(true_ohlcv[:, 3], pred_ohlcv[:, 3]),
            "RMSE_close": _rmse(true_ohlcv[:, 3], pred_ohlcv[:, 3]),
            "MAE_volume": _mae(true_ohlcv[:, 4], pred_ohlcv[:, 4]),
            "RMSE_volume": _rmse(true_ohlcv[:, 4], pred_ohlcv[:, 4]),
        }
        mean_true = np.mean(true_ohlcv[:, :4], axis=1)
        mean_pred = np.mean(pred_ohlcv[:, :4], axis=1)
        metrics_ohlcv["MAE_mean_ohlc"] = _mae(mean_true, mean_pred)
        metrics_ohlcv["RMSE_mean_ohlc"] = _rmse(mean_true, mean_pred)
        metrics_ohlcv["invalid_candle_rate_pred"] = _invalid_candle_rate(
            open_=pred_ohlcv[:, 0],
            high=pred_ohlcv[:, 1],
            low=pred_ohlcv[:, 2],
            close=pred_ohlcv[:, 3],
        )
        metrics_ohlcv["invalid_volume_rate_pred"] = _invalid_volume_rate(pred_ohlcv[:, 4])

    def _finite_or_none(x):
        try:
            x = float(x)
        except Exception:
            return None
        return x if np.isfinite(x) else None

    trained_at = datetime.now(timezone.utc)
    data_start = pd.to_datetime(min(ts), utc=True).to_pydatetime()
    data_end = pd.to_datetime(max(ts), utc=True).to_pydatetime()

    model_dir = os.path.join(os.getcwd(), "model_store")
    os.makedirs(model_dir, exist_ok=True)
    artifact = ModelArtifact(
        market_id=m.id,
        interval=interval,
        name=f"transformer_{feature_set}",
        trained_at=trained_at,
        data_start=data_start,
        data_end=data_end,
        target="ohlcv_structured",
        feature_set=feature_set,
        window_size_days=lookback,
        horizon_days=1,
        storage_provider="local",
        storage_uri="",
        checksum="",
        is_active=True,
        training_params={
            "lookback": lookback,
            "lr": float(lr),
            "weight_decay": float(weight_decay),
            "batch_size": int(batch_size),
            "max_epochs": int(max_epochs),
            "min_epochs": int(min_epochs),
            "patience": int(patience),
            "min_delta": float(min_delta),
            "seed": int(seed),
            "in_features": int(X_seq.shape[2]),
            "holdout_from": str(holdout_from),
            "optimizer": "AdamW",
            "loss": "SmoothL1Loss",
            "feature_cols": list(FULL_FEATURE_COLS),
            "model_hparams": {
                "d_model": 64,
                "n_heads": 4,
                "n_layers": 3,
                "ff_dim": 128,
                "dropout": 0.2,
                "out_dim": 5,
            },
            "x_mean": [float(v) for v in x_mean],
            "x_std": [float(v) for v in x_std],
            "y_mean": [float(v) for v in y_mean],
            "y_std": [float(v) for v in y_std],
        },
        metrics={
            "mse_components_val": _finite_or_none(mse_val),
            "mae_close_val": _finite_or_none(mae_close),
            "rmse_close_val": _finite_or_none(rmse_close),
            "features_used": list(FULL_FEATURE_COLS),
            "metrics_ohlcv_val": metrics_ohlcv,
            "train_loss_last": _finite_or_none(history["train_loss"][-1] if history["train_loss"] else float("nan")),
            "val_loss_last": _finite_or_none(history["val_loss"][-1] if history["val_loss"] else float("nan")),
            "best_val_loss": _finite_or_none(best_val),
            "best_epoch": int(best_epoch) if best_epoch is not None else None,
            "epochs_trained": int(len(history["train_loss"])),
        },
    )

    db.query(ModelArtifact).filter(
        ModelArtifact.market_id == m.id,
        ModelArtifact.interval == interval,
        ModelArtifact.target == "ohlcv_structured",
        ModelArtifact.is_active == True,
    ).update({"is_active": False})
    db.add(artifact)
    db.flush()

    out_path = os.path.join(model_dir, f"{artifact.id}.pt")
    torch.save(
        {
            "state_dict": model.state_dict(),
            "in_features": int(X_seq.shape[2]),
            "x_mean": x_mean.astype(np.float32),
            "x_std": x_std.astype(np.float32),
            "y_mean": y_mean.astype(np.float32),
            "y_std": y_std.astype(np.float32),
        },
        out_path,
    )
    artifact.storage_uri = out_path
    artifact.checksum = _sha256_file(out_path)
    db.commit()
    db.refresh(artifact)
    return artifact
