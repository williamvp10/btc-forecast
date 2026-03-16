from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import torch
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models.metadata import Market
from app.db.models.ml import ModelArtifact, Prediction
from app.db.models.timeseries import Candle, Feature, FgiDaily, MacroDaily
from app.services.ml.training import FULL_FEATURE_COLS
from app.services.ml.transformer import TransformerEncoderRegressor
from app.services.features import build_feature_frame, filter_feature_set


def _finite_or_none(x):
    try:
        x = float(x)
    except Exception:
        return None
    return x if np.isfinite(x) else None


def _finite_or_zero(x) -> float:
    v = _finite_or_none(x)
    return 0.0 if v is None else float(v)


def _reconstruct_levels(close_t: float, comps: np.ndarray) -> dict:
    gap_open, logret_close, high_excess, low_excess, logvol = comps.tolist()
    gap_open = float(np.clip(_finite_or_zero(gap_open), -20.0, 20.0))
    logret_close = float(np.clip(_finite_or_zero(logret_close), -20.0, 20.0))
    high_excess = float(np.clip(_finite_or_zero(high_excess), -20.0, 20.0))
    low_excess = float(np.clip(_finite_or_zero(low_excess), -20.0, 20.0))
    logvol = float(np.clip(_finite_or_zero(logvol), -20.0, 20.0))
    open_tp1 = float(close_t * np.exp(gap_open))
    close_tp1 = float(close_t * np.exp(logret_close))
    high_tp1 = float(max(open_tp1, close_tp1) + np.expm1(high_excess))
    low_tp1 = float(min(open_tp1, close_tp1) - np.expm1(low_excess))
    volume_tp1 = float(max(np.expm1(logvol), 0.0))
    levels = {"open": open_tp1, "high": high_tp1, "low": low_tp1, "close": close_tp1, "volume": volume_tp1}
    if not all(np.isfinite([levels["open"], levels["high"], levels["low"], levels["close"], levels["volume"]])):
        v = float(close_t)
        return {"open": v, "high": v, "low": v, "close": v, "volume": 0.0}
    return levels


def _load_model_bundle(artifact: ModelArtifact) -> tuple[TransformerEncoderRegressor, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    ckpt = torch.load(artifact.storage_uri, map_location="cpu", weights_only=False)
    in_features = int(ckpt["in_features"])
    model = TransformerEncoderRegressor(in_features=in_features)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    x_mean = ckpt.get("x_mean")
    x_std = ckpt.get("x_std")
    y_mean = ckpt.get("y_mean")
    y_std = ckpt.get("y_std")
    if x_mean is None or x_std is None or y_mean is None or y_std is None:
        x_mean = np.zeros(in_features, dtype=np.float32)
        x_std = np.ones(in_features, dtype=np.float32)
        y_mean = np.zeros(5, dtype=np.float32)
        y_std = np.ones(5, dtype=np.float32)
    x_mean = np.asarray(x_mean, dtype=np.float32)
    x_std = np.asarray(x_std, dtype=np.float32)
    y_mean = np.asarray(y_mean, dtype=np.float32)
    y_std = np.asarray(y_std, dtype=np.float32)
    return model, x_mean, x_std, y_mean, y_std


def get_active_model(db: Session, *, market_id: int, interval: str) -> ModelArtifact | None:
    return (
        db.query(ModelArtifact)
        .filter(
            ModelArtifact.market_id == market_id,
            ModelArtifact.interval == interval,
            ModelArtifact.target == "ohlcv_structured",
            ModelArtifact.is_active == True,
        )
        .order_by(ModelArtifact.trained_at.desc())
        .first()
    )


def predict_next_day(db: Session, *, symbol: str = "XBX-USD", interval: str = "1d") -> Prediction:
    m = db.query(Market).filter(Market.symbol == symbol).first()
    if not m:
        raise ValueError("Market not found")

    artifact = get_active_model(db, market_id=m.id, interval=interval)
    if not artifact:
        raise ValueError("No active model")

    last_candle = (
        db.query(Candle)
        .filter(Candle.market_id == m.id, Candle.interval == interval)
        .order_by(Candle.open_time.desc())
        .first()
    )
    if not last_candle:
        raise ValueError("No candles available")

    as_of_time = pd.to_datetime(last_candle.open_time, utc=True).to_pydatetime()
    target_time = (pd.to_datetime(as_of_time, utc=True) + pd.Timedelta(days=1)).to_pydatetime()

    existing = (
        db.query(Prediction)
        .filter(
            Prediction.model_id == artifact.id,
            Prediction.market_id == m.id,
            Prediction.as_of_time == as_of_time,
            Prediction.target_time == target_time,
        )
        .first()
    )
    if existing:
        return existing

    feats = (
        db.query(Feature)
        .filter(Feature.market_id == m.id, Feature.interval == interval, Feature.feature_set == artifact.feature_set)
        .filter(Feature.open_time <= as_of_time)
        .order_by(Feature.open_time.desc())
        .limit(int(artifact.window_size_days))
        .all()
    )
    if len(feats) < int(artifact.window_size_days):
        raise ValueError("Not enough features for inference")

    feats = list(reversed(feats))
    X = []
    for f in feats:
        row = f.values or {}
        X.append([float(row.get(c)) for c in FULL_FEATURE_COLS])
    X = np.array(X, dtype=np.float32)[None, :, :]

    model, x_mean, x_std, y_mean, y_std = _load_model_bundle(artifact)
    with torch.no_grad():
        Xn = (X - x_mean[None, None, :]) / x_std[None, None, :]
        y_hat_s = model(torch.tensor(Xn)).cpu().numpy()[0]
        y_hat = (y_hat_s * y_std) + y_mean

    levels = _reconstruct_levels(float(last_candle.close), y_hat)
    pred = Prediction(
        model_id=artifact.id,
        market_id=m.id,
        as_of_time=as_of_time,
        target_time=target_time,
        horizon_days=1,
        pred_open=levels["open"],
        pred_high=levels["high"],
        pred_low=levels["low"],
        pred_close=levels["close"],
        pred_volume=levels["volume"],
        pred_components={
            "gap_open": _finite_or_none(y_hat[0]),
            "logret_close": _finite_or_none(y_hat[1]),
            "high_excess": _finite_or_none(y_hat[2]),
            "low_excess": _finite_or_none(y_hat[3]),
            "logvol": _finite_or_none(y_hat[4]),
        },
        generated_at=datetime.now(timezone.utc),
    )
    db.add(pred)
    db.commit()
    db.refresh(pred)
    return pred


def _get_last_exog(db: Session, *, as_of_time: datetime) -> tuple[dict, dict]:
    fgi = (
        db.query(FgiDaily)
        .filter(FgiDaily.open_time <= as_of_time)
        .order_by(FgiDaily.open_time.desc())
        .first()
    )
    macro = (
        db.query(MacroDaily)
        .filter(MacroDaily.open_time <= as_of_time)
        .order_by(MacroDaily.open_time.desc())
        .first()
    )

    fgi_vals = {"fgi": None, "fgi_norm": None}
    if fgi:
        fgi_vals = {"fgi": fgi.fgi, "fgi_norm": fgi.fgi_norm}

    macro_vals = {}
    if macro:
        for col in MacroDaily.__table__.columns:
            if col.name in ["id", "open_time"]:
                continue
            macro_vals[col.name] = getattr(macro, col.name)

    return fgi_vals, macro_vals


def _build_feature_matrix(
    candles_df: pd.DataFrame,
    *,
    fgi_vals: dict,
    macro_vals: dict,
    feature_set: str,
    lookback: int,
) -> np.ndarray:
    df = candles_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.floor("D")

    fgi_df = pd.DataFrame(
        [{"timestamp": ts, **fgi_vals} for ts in df["timestamp"].tolist()]
    )

    df_feat = build_feature_frame(df, fgi_df)
    if macro_vals:
        macro_df = pd.DataFrame([{"timestamp": ts, **macro_vals} for ts in df_feat["timestamp"].tolist()])
        df_feat = df_feat.merge(macro_df, on="timestamp", how="left")

    df_set = filter_feature_set(df_feat, feature_set=feature_set)
    if len(df_set) < lookback:
        raise ValueError("Not enough feature rows for inference")

    X = df_set.tail(lookback)[FULL_FEATURE_COLS].astype(float).to_numpy(dtype=np.float32)[None, :, :]
    return X


def predict_horizon(
    db: Session,
    *,
    symbol: str = "XBX-USD",
    interval: str = "1d",
    horizon_days: int = 7,
) -> tuple[list[Prediction], int]:
    if interval != "1d":
        raise ValueError("Only interval=1d supported")
    if horizon_days < 1 or horizon_days > 7:
        raise ValueError("horizon_days must be between 1 and 7")

    m = db.query(Market).filter(Market.symbol == symbol).first()
    if not m:
        raise ValueError("Market not found")

    artifact = get_active_model(db, market_id=m.id, interval=interval)
    if not artifact:
        raise ValueError("No active model")

    last_candle = (
        db.query(Candle)
        .filter(Candle.market_id == m.id, Candle.interval == interval)
        .order_by(Candle.open_time.desc())
        .first()
    )
    if not last_candle:
        raise ValueError("No candles available")

    as_of_time = pd.to_datetime(last_candle.open_time, utc=True).to_pydatetime()
    generated_at = datetime.now(timezone.utc)

    fgi_vals, macro_vals = _get_last_exog(db, as_of_time=as_of_time)

    base_candles = (
        db.query(Candle)
        .filter(Candle.market_id == m.id, Candle.interval == interval, Candle.open_time <= as_of_time)
        .order_by(Candle.open_time.asc())
        .limit(5000)
        .all()
    )
    candles_df = pd.DataFrame(
        [{"timestamp": c.open_time, "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume} for c in base_candles]
    )
    candles_df["timestamp"] = pd.to_datetime(candles_df["timestamp"], utc=True).dt.floor("D")
    candles_df = candles_df.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp").reset_index(drop=True)

    model, x_mean, x_std, y_mean, y_std = _load_model_bundle(artifact)

    preds: list[Prediction] = []
    created = 0
    for step in range(1, int(horizon_days) + 1):
        target_time = (pd.to_datetime(as_of_time, utc=True) + pd.Timedelta(days=step)).to_pydatetime()

        existing = (
            db.query(Prediction)
            .filter(
                Prediction.model_id == artifact.id,
                Prediction.market_id == m.id,
                Prediction.as_of_time == as_of_time,
                Prediction.target_time == target_time,
            )
            .first()
        )
        if existing:
            preds.append(existing)
            candles_df = pd.concat(
                [
                    candles_df,
                    pd.DataFrame(
                        [
                            {
                                "timestamp": pd.to_datetime(existing.target_time, utc=True),
                                "open": existing.pred_open,
                                "high": existing.pred_high,
                                "low": existing.pred_low,
                                "close": existing.pred_close,
                                "volume": existing.pred_volume,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
            continue

        window = candles_df.tail(max(int(artifact.window_size_days) + 140, 200)).reset_index(drop=True)
        X = _build_feature_matrix(
            window,
            fgi_vals=fgi_vals,
            macro_vals=macro_vals,
            feature_set=artifact.feature_set,
            lookback=int(artifact.window_size_days),
        )
        with torch.no_grad():
            Xn = (X - x_mean[None, None, :]) / x_std[None, None, :]
            y_hat_s = model(torch.tensor(Xn)).cpu().numpy()[0]
            y_hat = (y_hat_s * y_std) + y_mean

        close_t = float(window.iloc[-1]["close"])
        levels = _reconstruct_levels(close_t, y_hat)

        pred = Prediction(
            model_id=artifact.id,
            market_id=m.id,
            as_of_time=as_of_time,
            target_time=target_time,
            horizon_days=step,
            pred_open=levels["open"],
            pred_high=levels["high"],
            pred_low=levels["low"],
            pred_close=levels["close"],
            pred_volume=levels["volume"],
            pred_components={
                "gap_open": _finite_or_none(y_hat[0]),
                "logret_close": _finite_or_none(y_hat[1]),
                "high_excess": _finite_or_none(y_hat[2]),
                "low_excess": _finite_or_none(y_hat[3]),
                "logvol": _finite_or_none(y_hat[4]),
            },
            generated_at=generated_at,
        )
        db.add(pred)
        db.flush()
        preds.append(pred)
        created += 1

        candles_df = pd.concat(
            [
                candles_df,
                pd.DataFrame(
                    [
                        {
                            "timestamp": pd.to_datetime(target_time, utc=True),
                            "open": pred.pred_open,
                            "high": pred.pred_high,
                            "low": pred.pred_low,
                            "close": pred.pred_close,
                            "volume": pred.pred_volume,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )

    db.commit()
    for p in preds:
        db.refresh(p)
    return preds, created
