import os
import pathlib

import pandas as pd
import requests
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.timeseries import Candle, FgiDaily
from app.services.ingestion import (
    upsert_market,
    ingest_coindesk_candles_1d_from_csv,
    fetch_fgi_history,
)
from app.services.coindesk import download_all_days, download_days_since, standardize_ohlcv


def _max_candle_time(db: Session, market_id: int, interval: str) -> pd.Timestamp | None:
    v = (
        db.query(func.max(Candle.open_time))
        .filter(Candle.market_id == market_id, Candle.interval == interval)
        .scalar()
    )
    if v is None:
        return None
    return pd.to_datetime(v, utc=True)


def _max_fgi_time(db: Session) -> pd.Timestamp | None:
    v = db.query(func.max(FgiDaily.open_time)).scalar()
    if v is None:
        return None
    return pd.to_datetime(v, utc=True)


def sync_candles_1d_from_csv(
    db: Session,
    candles_csv_path: str,
    *,
    symbol: str = "XBX-USD",
    interval: str = "1d",
    lookback_days: int = 3,
) -> int:
    m = upsert_market(db, symbol=symbol)
    last = _max_candle_time(db, m.id, interval=interval)

    if last is None:
        return ingest_coindesk_candles_1d_from_csv(db, candles_csv_path, m.id)

    cutoff = last - pd.Timedelta(days=int(lookback_days))
    df = pd.read_csv(candles_csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df[df["timestamp"] >= cutoff].reset_index(drop=True)
    if len(df) == 0:
        return 0

    tmp_path = candles_csv_path + ".sync_tmp.csv"
    df.to_csv(tmp_path, index=False)
    return ingest_coindesk_candles_1d_from_csv(db, tmp_path, m.id)


def sync_fgi_daily_from_api(db: Session, *, lookback_days: int = 3) -> int:
    last = _max_fgi_time(db)
    df = fetch_fgi_history()
    if len(df) == 0:
        return 0

    if last is not None:
        cutoff = last - pd.Timedelta(days=int(lookback_days))
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df[df["timestamp"] >= cutoff].reset_index(drop=True)
        if len(df) == 0:
            return 0

    rows = []
    for _, row in df.iterrows():
        rows.append(
            {
                "open_time": row["timestamp"],
                "fgi": None if pd.isna(row["fgi"]) else int(row["fgi"]),
                "fgi_norm": None if pd.isna(row["fgi_norm"]) else float(row["fgi_norm"]),
            }
        )

    from sqlalchemy.dialects.postgresql import insert

    stmt = insert(FgiDaily).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_fgi_daily_open_time",
        set_={"fgi": stmt.excluded.fgi, "fgi_norm": stmt.excluded.fgi_norm},
    )
    db.execute(stmt)
    db.commit()
    return int(len(rows))


def _ensure_parent(path: str) -> None:
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)


def _merge_write_csv(csv_path: str, df_new: pd.DataFrame) -> None:
    _ensure_parent(csv_path)
    if os.path.exists(csv_path):
        df_old = pd.read_csv(csv_path)
        if "timestamp" in df_old.columns:
            df_old["timestamp"] = pd.to_datetime(df_old["timestamp"], utc=True)
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new.copy()

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp").reset_index(drop=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.strftime("%Y-%m-%d %H:%M:%S+00:00")
    df.to_csv(csv_path, index=False)


def sync_candles_1d_from_coindesk(
    db: Session,
    *,
    candles_csv_path: str,
    symbol: str = "XBX-USD",
    market: str = "cadli",
    interval: str = "1d",
) -> dict:
    if interval != "1d":
        raise ValueError("Only interval=1d is supported")

    m = upsert_market(db, symbol=symbol)
    last = _max_candle_time(db, m.id, interval=interval)

    session = requests.Session()
    if last is None:
        df_raw, _meta = download_all_days(session, market=market, instrument=symbol)
        df_clean = standardize_ohlcv(df_raw)
        _merge_write_csv(candles_csv_path, df_clean[["timestamp", "open", "high", "low", "close", "volume"]])
        tmp_path = candles_csv_path + ".bootstrap_tmp.csv"
        df_clean[["timestamp", "open", "high", "low", "close", "volume"]].to_csv(tmp_path, index=False)
        rows = ingest_coindesk_candles_1d_from_csv(db, tmp_path, m.id)
        return {"mode": "bootstrap", "last_db": None, "rows": int(rows)}

    df_inc = download_days_since(session, market=market, instrument=symbol, last_ts=last)
    if len(df_inc) == 0:
        return {"mode": "sync", "last_db": last.isoformat(), "rows": 0}

    _merge_write_csv(candles_csv_path, df_inc[["timestamp", "open", "high", "low", "close", "volume"]])
    tmp_path = candles_csv_path + ".sync_tmp.csv"
    df_inc[["timestamp", "open", "high", "low", "close", "volume"]].to_csv(tmp_path, index=False)
    rows = ingest_coindesk_candles_1d_from_csv(db, tmp_path, m.id)
    return {"mode": "sync", "last_db": last.isoformat(), "rows": int(rows)}


def sync_fgi_daily_with_csv(db: Session, *, fgi_csv_path: str, lookback_days: int = 3) -> dict:
    last = _max_fgi_time(db)
    df = fetch_fgi_history()
    if len(df) == 0:
        return {"mode": "sync", "last_db": last.isoformat() if last is not None else None, "rows": 0}

    if last is None:
        _merge_write_csv(fgi_csv_path, df[["timestamp", "fgi", "fgi_norm"]])
        rows = sync_fgi_daily_from_api(db, lookback_days=99999)
        return {"mode": "bootstrap", "last_db": None, "rows": int(rows)}

    cutoff = last - pd.Timedelta(days=int(lookback_days))
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df[df["timestamp"] >= cutoff].reset_index(drop=True)
    if len(df) == 0:
        return {"mode": "sync", "last_db": last.isoformat(), "rows": 0}

    _merge_write_csv(fgi_csv_path, df[["timestamp", "fgi", "fgi_norm"]])
    rows = sync_fgi_daily_from_api(db, lookback_days=lookback_days)
    return {"mode": "sync", "last_db": last.isoformat(), "rows": int(rows)}


def sync_daily(
    db: Session,
    *,
    candles_csv_path: str,
    fgi_csv_path: str | None = None,
    symbol: str = "XBX-USD",
    coindesk_market: str = "sda",
    interval: str = "1d",
    lookback_days: int = 3,
) -> dict:
    fgi_csv_path = fgi_csv_path or os.path.join(os.path.dirname(candles_csv_path), "external_1d__sent.csv")

    candles_out = sync_candles_1d_from_coindesk(
        db,
        candles_csv_path=candles_csv_path,
        symbol=symbol,
        market=coindesk_market,
        interval=interval,
    )
    fgi_out = sync_fgi_daily_with_csv(db, fgi_csv_path=fgi_csv_path, lookback_days=lookback_days)
    return {"candles": candles_out, "fgi": fgi_out, "candles_csv_path": candles_csv_path, "fgi_csv_path": fgi_csv_path}
