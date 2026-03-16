import os
from typing import Any

import pandas as pd
import requests

BASE_URL = "https://data-api.coindesk.com"


def _headers() -> dict[str, str]:
    api_key = os.getenv("COINDESK_API_KEY") or os.getenv("COINDESK_APIKEY") or os.getenv("COINDESK_KEY")
    if not api_key:
        return {}
    return {"Authorization": f"Apikey {api_key}", "x-api-key": api_key}


def fetch_market_instrument_metadata(session: requests.Session, *, market: str, instrument: str) -> dict[str, Any] | None:
    url = f"{BASE_URL}/index/cc/v1/markets/instruments"
    params = {"market": market, "instruments": instrument, "instrument_status": "ACTIVE"}
    r = session.get(url, params=params, headers=_headers(), timeout=30)
    r.raise_for_status()
    payload = r.json()
    data = payload.get("Data") or payload.get("data")

    if isinstance(data, dict):
        market_node = data.get(market)
        if isinstance(market_node, dict):
            instruments = market_node.get("instruments") or market_node.get("Instruments")
            if isinstance(instruments, dict):
                row = instruments.get(instrument) or instruments.get(instrument.replace("-", ""))
                if isinstance(row, dict):
                    return row
        row = data.get(instrument)
        if isinstance(row, dict):
            return row

    if isinstance(data, list):
        for row in data:
            if row.get("INSTRUMENT") == instrument or row.get("instrument") == instrument:
                return row

    return None


def fetch_endpoint(
    session: requests.Session,
    endpoint: str,
    *,
    market: str,
    instrument: str,
    limit: int,
    to_ts: int | None = None,
) -> dict[str, Any]:
    url = f"{BASE_URL}{endpoint}"
    params: dict[str, Any] = {"market": market, "instrument": instrument, "limit": int(limit), "groups": "OHLC,VOLUME"}
    if to_ts is not None:
        params["to_ts"] = int(to_ts)
    r = session.get(url, params=params, headers=_headers(), timeout=30)
    try:
        payload = r.json()
    except Exception:
        payload = {"Data": [], "Err": {"message": r.text}}
    payload["_http_status"] = r.status_code
    if r.status_code >= 400 and r.status_code != 404:
        r.raise_for_status()
    return payload


def standardize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    col_map = {
        "TIMESTAMP": "timestamp",
        "OPEN": "open",
        "HIGH": "high",
        "LOW": "low",
        "CLOSE": "close",
        "VOLUME": "volume",
        "QUOTE_VOLUME": "quote_volume",
    }
    for k, v in col_map.items():
        if k in df.columns:
            df = df.rename(columns={k: v})

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)

    for c in ["open", "high", "low", "close", "volume", "quote_volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
    df["high"] = df[["high", "open", "close"]].max(axis=1)
    df["low"] = df[["low", "open", "close"]].min(axis=1)
    df = df.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp").reset_index(drop=True)
    return df


def download_all_days(
    session: requests.Session,
    *,
    market: str,
    instrument: str,
    limit: int = 2000,
    max_pages: int = 500,
) -> tuple[pd.DataFrame, dict[str, Any] | None]:
    meta = fetch_market_instrument_metadata(session, market=market, instrument=instrument)
    oldest_allowed = None
    if meta:
        cand = meta.get("OLDEST_HISTORICAL_DAY_DATA_TIMESTAMP") or meta.get("FIRST_INDEX_UPDATE_TIMESTAMP")
        if cand is not None:
            oldest_allowed = int(cand)

    all_rows: list[dict[str, Any]] = []
    to_ts = None
    for _ in range(int(max_pages)):
        payload = fetch_endpoint(
            session,
            "/index/cc/v1/historical/days",
            market=market,
            instrument=instrument,
            limit=limit,
            to_ts=to_ts,
        )
        if payload.get("_http_status") == 404:
            break
        data = payload.get("Data") or payload.get("data") or []
        if not data:
            break
        all_rows.extend(data)
        ts_vals = [d.get("TIMESTAMP") for d in data if d.get("TIMESTAMP") is not None]
        if not ts_vals:
            break
        oldest = int(min(ts_vals))
        if oldest_allowed is not None and oldest <= oldest_allowed:
            break
        next_to = oldest - 86400
        if to_ts is not None and next_to >= to_ts:
            break
        to_ts = next_to

    df = pd.DataFrame(all_rows)
    return df, meta


def download_days_since(
    session: requests.Session,
    *,
    market: str,
    instrument: str,
    last_ts: pd.Timestamp,
    limit: int = 2000,
    max_pages: int = 30,
) -> pd.DataFrame:
    last_ts = pd.to_datetime(last_ts, utc=True)
    last_epoch = int(last_ts.timestamp())

    rows: list[dict[str, Any]] = []
    to_ts = int(pd.Timestamp.now(tz="UTC").timestamp())
    for _ in range(int(max_pages)):
        payload = fetch_endpoint(
            session,
            "/index/cc/v1/historical/days",
            market=market,
            instrument=instrument,
            limit=limit,
            to_ts=to_ts,
        )
        if payload.get("_http_status") == 404:
            break
        data = payload.get("Data") or payload.get("data") or []
        if not data:
            break
        rows.extend(data)
        ts_vals = [d.get("TIMESTAMP") for d in data if d.get("TIMESTAMP") is not None]
        if not ts_vals:
            break
        oldest = int(min(ts_vals))
        if oldest <= last_epoch:
            break
        to_ts = oldest - 86400

    df = pd.DataFrame(rows)
    df = standardize_ohlcv(df)
    if len(df) == 0:
        return df
    df = df[df["timestamp"] > last_ts].reset_index(drop=True)
    return df
