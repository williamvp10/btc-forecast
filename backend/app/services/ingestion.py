import logging
import pandas as pd
import requests
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from app.db.models.metadata import Market
from app.db.models.timeseries import Candle, FgiDaily

logger = logging.getLogger(__name__)

def upsert_market(
    db: Session,
    symbol: str = "XBX-USD",
    base_asset: str = "BTC",
    quote_asset: str = "USD",
    source: str = "coindesk_xbx",
) -> Market:
    m = db.query(Market).filter(Market.symbol == symbol).first()
    if m:
        return m
    m = Market(symbol=symbol, base_asset=base_asset, quote_asset=quote_asset, source=source)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def ingest_coindesk_candles_1d_from_csv(db: Session, csv_path: str, market_id: int) -> int:
    df = pd.read_csv(csv_path)
    if "timestamp" not in df.columns:
        raise ValueError("CSV missing 'timestamp' column")
    required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
    if not all(c in df.columns for c in required_cols):
        raise ValueError(f"CSV missing required columns: {required_cols}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.dropna(subset=required_cols)
    df = df.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp").reset_index(drop=True)

    rows = []
    for _, row in df.iterrows():
        rows.append(
            {
                "market_id": market_id,
                "interval": "1d",
                "open_time": row["timestamp"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
        )

    if not rows:
        return 0

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
    db.commit()
    return int(len(rows))


def fetch_fgi_history() -> pd.DataFrame:
    url = "https://api.alternative.me/fng/"
    params = {"limit": 0, "format": "json", "date_format": "us"}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json().get("data") or []
    df = pd.DataFrame(data)
    if len(df) == 0:
        return pd.DataFrame(columns=["timestamp", "fgi", "fgi_norm"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="%m-%d-%Y", errors="coerce")
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize("UTC")
    df["fgi"] = pd.to_numeric(df["value"], errors="coerce")
    df = df[["timestamp", "fgi"]].dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    df["fgi_norm"] = df["fgi"] / 100.0
    df["timestamp"] = df["timestamp"].dt.floor("D")
    df = df.drop_duplicates(subset=["timestamp"], keep="last")
    return df


def ingest_fgi_daily_from_api(db: Session) -> int:
    df = fetch_fgi_history()
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
    stmt = insert(FgiDaily).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_fgi_daily_open_time",
        set_={"fgi": stmt.excluded.fgi, "fgi_norm": stmt.excluded.fgi_norm},
    )
    db.execute(stmt)
    db.commit()
    return int(len(rows))
