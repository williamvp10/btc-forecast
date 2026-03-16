import hashlib
import logging
from datetime import datetime, timezone

import pandas as pd
import numpy as np
import json
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models.metadata import Market
from app.db.models.timeseries import Candle, FgiDaily, MacroDaily, Feature
from app.services.coindesk import download_all_days, download_days_since, standardize_ohlcv
from app.services.ingestion import fetch_fgi_history, upsert_market
from app.services.macro import fetch_macro_daily
from app.services.features import build_feature_frame, filter_feature_set
import requests


logger = logging.getLogger(__name__)

def _json_number(v):
    if v is None:
        return None
    if callable(v):
        return None
    if isinstance(v, (np.generic,)):
        return v.item()
    if isinstance(v, (pd.Timestamp,)):
        return v.to_pydatetime().isoformat()
    return v


def _max_candle_time(db: Session, market_id: int, interval: str) -> pd.Timestamp | None:
    v = (
        db.query(func.max(Candle.open_time))
        .filter(Candle.market_id == market_id, Candle.interval == interval)
        .scalar()
    )
    if v is None:
        return None
    return pd.to_datetime(v, utc=True)


def refresh_candles_1d(db: Session, *, symbol: str = "XBX-USD", coindesk_market: str = "sda") -> int:
    m = upsert_market(db, symbol=symbol)
    last = _max_candle_time(db, m.id, "1d")
    count = db.query(func.count(Candle.id)).filter(Candle.market_id == m.id, Candle.interval == "1d").scalar() or 0

    session = requests.Session()
    if last is None or int(count) < 200:
        df_raw, _ = download_all_days(session, market=coindesk_market, instrument=symbol)
        df_clean = standardize_ohlcv(df_raw)
    else:
        df_clean = download_days_since(session, market=coindesk_market, instrument=symbol, last_ts=last)

    if len(df_clean) == 0:
        return 0

    df_clean = df_clean[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    rows = []
    for _, row in df_clean.iterrows():
        rows.append(
            {
                "market_id": m.id,
                "interval": "1d",
                "open_time": pd.to_datetime(row["timestamp"], utc=True).to_pydatetime(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
        )

    stmt = insert(Candle).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_candle_market_interval_time",
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
        },
    )
    db.execute(stmt)
    return int(len(rows))


def refresh_fgi_daily(db: Session) -> int:
    df = fetch_fgi_history()
    if len(df) == 0:
        return 0
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.floor("D")
    df = df.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp").reset_index(drop=True)

    rows = []
    for _, row in df.iterrows():
        rows.append(
            {
                "open_time": pd.to_datetime(row["timestamp"], utc=True).to_pydatetime(),
                "fgi": None if pd.isna(row["fgi"]) else int(row["fgi"]),
                "fgi_norm": None if pd.isna(row["fgi_norm"]) else float(row["fgi_norm"]),
            }
        )
    stmt = insert(FgiDaily).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_fgi_daily_open_time",
        set_={"fgi": stmt.excluded.fgi, "fgi_norm": stmt.excluded.fgi_norm},
    )
    db.execute(stmt)
    return int(len(rows))


def refresh_macro_daily(db: Session, *, market_id: int, interval: str = "1d") -> int:
    candles = (
        db.query(Candle.open_time)
        .filter(Candle.market_id == market_id, Candle.interval == interval)
        .order_by(Candle.open_time.asc())
        .all()
    )
    if not candles:
        return 0
    btc_days = pd.DatetimeIndex([pd.to_datetime(c[0], utc=True).floor("D") for c in candles], tz="UTC")
    btc_days = btc_days.unique().sort_values()

    df_macro = fetch_macro_daily(btc_days)
    if len(df_macro) == 0:
        return 0

    rows = []
    for _, row in df_macro.iterrows():
        d = row.to_dict()
        ts = pd.to_datetime(d.pop("timestamp"), utc=True).to_pydatetime()
        rows.append({"open_time": ts, **{k: (None if pd.isna(v) else float(v)) for k, v in d.items()}})

    stmt = insert(MacroDaily).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_macro_daily_open_time",
        set_={c.name: getattr(stmt.excluded, c.name) for c in MacroDaily.__table__.columns if c.name not in ["id", "open_time"]},
    )
    db.execute(stmt)
    return int(len(rows))


def compute_and_store_features(
    db: Session,
    *,
    symbol: str = "XBX-USD",
    interval: str = "1d",
    feature_set: str = "full",
) -> int:
    if interval != "1d":
        raise ValueError("Only interval=1d supported")

    m = db.query(Market).filter(Market.symbol == symbol).first()
    if not m:
        m = upsert_market(db, symbol=symbol)

    candles = (
        db.query(Candle)
        .filter(Candle.market_id == m.id, Candle.interval == interval)
        .order_by(Candle.open_time.asc())
        .all()
    )
    if not candles:
        return 0

    candles_df = pd.DataFrame(
        [
            {
                "timestamp": c.open_time,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]
    )

    fgi_rows = db.query(FgiDaily).order_by(FgiDaily.open_time.asc()).all()
    fgi_df = pd.DataFrame(
        [{"timestamp": r.open_time, "fgi": r.fgi, "fgi_norm": r.fgi_norm} for r in fgi_rows]
    ) if fgi_rows else pd.DataFrame(columns=["timestamp", "fgi", "fgi_norm"])

    macro_rows = db.query(MacroDaily).order_by(MacroDaily.open_time.asc()).all()
    macro_df = (
        pd.DataFrame([{c.name: getattr(r, c.name) for c in MacroDaily.__table__.columns if c.name != "id"} for r in macro_rows])
        if macro_rows
        else pd.DataFrame(columns=["open_time"])
    )
    if len(macro_df) > 0:
        macro_df = macro_df.rename(columns={"open_time": "timestamp"})

    df = build_feature_frame(candles_df, fgi_df if len(fgi_df) else None)
    if len(macro_df) > 0:
        macro_df["timestamp"] = pd.to_datetime(macro_df["timestamp"], utc=True).dt.floor("D")
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.floor("D")
        df = df.merge(macro_df, on="timestamp", how="left")

    df_set = filter_feature_set(df, feature_set=feature_set)
    if len(df_set) == 0:
        return 0

    rows = []
    for _, row in df_set.iterrows():
        values = row.to_dict()
        ts = pd.to_datetime(values.pop("timestamp"), utc=True).to_pydatetime()
        clean = {k: _json_number(None if pd.isna(v) else v) for k, v in values.items()}
        clean = json.loads(json.dumps(clean, default=lambda _o: None, allow_nan=True))
        rows.append({"market_id": m.id, "interval": interval, "open_time": ts, "feature_set": feature_set, "values": clean})

    stmt = insert(Feature).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_feature_market_interval_time_set",
        set_={"values": stmt.excluded["values"]},
    )
    db.execute(stmt)
    return int(len(rows))


def refresh_all_and_features(
    db: Session,
    *,
    symbol: str = "XBX-USD",
    coindesk_market: str = "sda",
    feature_set: str = "full",
) -> dict:
    now = datetime.now(timezone.utc)
    m = upsert_market(db, symbol=symbol)

    candles_rows = refresh_candles_1d(db, symbol=symbol, coindesk_market=coindesk_market)
    fgi_rows = refresh_fgi_daily(db)
    macro_rows = refresh_macro_daily(db, market_id=m.id)
    feature_rows = compute_and_store_features(db, symbol=symbol, interval="1d", feature_set=feature_set)

    out = {
        "updated_at": now.isoformat(),
        "symbol": symbol,
        "candles_rows": int(candles_rows),
        "fgi_rows": int(fgi_rows),
        "macro_rows": int(macro_rows),
        "feature_rows": int(feature_rows),
    }
    logger.info("Refresh pipeline: %s", out)
    return out
