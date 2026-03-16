import numpy as np
import pandas as pd
import yfinance as yf


def fetch_macro_daily(btc_days: pd.DatetimeIndex) -> pd.DataFrame:
    tickers: dict[str, list[str]] = {
        "sp500": ["^GSPC"],
        "dxy": ["UUP", "DX-Y.NYB"],
        "vix": ["^VIX"],
        "gold": ["GC=F"],
    }

    if btc_days.tz is None:
        btc_days = btc_days.tz_localize("UTC")
    else:
        btc_days = btc_days.tz_convert("UTC")

    start_date = (btc_days.min() - pd.Timedelta(days=7)).date().isoformat()
    end_date = (btc_days.max() + pd.Timedelta(days=1)).date().isoformat()

    macro_frames: dict[str, pd.DataFrame] = {}
    for name, candidates in tickers.items():
        dfm = None
        for ticker in candidates:
            try:
                df_try = yf.download(ticker, start=start_date, end=end_date, progress=False)
            except Exception:
                df_try = None
            if df_try is None or len(df_try) == 0:
                continue
            if "Close" not in df_try.columns:
                continue
            dfm = df_try
            break

        if dfm is None or len(dfm) == 0:
            macro_frames[name] = pd.DataFrame(index=btc_days, columns=[name], dtype=float)
            continue

        dfm = dfm[["Close"]].copy()
        dfm.columns = [name]
        idx = pd.to_datetime(dfm.index)
        dfm.index = pd.DatetimeIndex(idx.date, tz="UTC")
        dfm = dfm[~dfm.index.duplicated(keep="last")].sort_index()
        dfm = dfm.reindex(btc_days)
        dfm[name] = pd.to_numeric(dfm[name], errors="coerce").ffill(limit=7)
        macro_frames[name] = dfm

    df_macro = pd.DataFrame(index=btc_days)
    for name, dfm in macro_frames.items():
        df_macro[name] = pd.to_numeric(dfm[name], errors="coerce")
        df_macro[f"log_ret_{name}"] = np.log(df_macro[name] / df_macro[name].shift(1))
        df_macro[f"vol_7d_{name}"] = df_macro[f"log_ret_{name}"].rolling(window=7).std()

    df_macro = df_macro.reset_index().rename(columns={"index": "timestamp"})
    df_macro["timestamp"] = pd.to_datetime(df_macro["timestamp"], utc=True).dt.floor("D")
    return df_macro
