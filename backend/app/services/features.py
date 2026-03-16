import numpy as np
import pandas as pd


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / (avg_loss + 1e-12)
    return 100 - (100 / (1 + rs))


def add_base_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["log_close"] = np.log(df["close"].astype(float))
    df["log_return"] = df["log_close"].diff()
    df["log_volume"] = np.log1p(df["volume"].astype(float))
    return df


def add_tech_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    for i in range(1, 8):
        df[f"log_ret_lag_{i}"] = df["log_return"].shift(i)

    df["volatility_7"] = df["log_return"].rolling(window=7).std(ddof=0)
    df["volatility_30"] = df["log_return"].rolling(window=30).std(ddof=0)

    df["rsi_14"] = compute_rsi(df["close"], period=14)

    for w in [8, 20, 100]:
        df[f"sma_{w}"] = df["close"].rolling(window=w).mean()
        df[f"ema_{w}"] = df["close"].ewm(span=w, adjust=False).mean()

    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)

    df["candle_range"] = (high - low) / (close.replace(0, np.nan))
    df["candle_body"] = (close - open_) / (open_.replace(0, np.nan))
    df["upper_wick"] = (high - np.maximum(open_, close)) / (close.replace(0, np.nan))
    df["lower_wick"] = (np.minimum(open_, close) - low) / (close.replace(0, np.nan))

    denom = (high - low).replace(0, np.nan)
    df["buying_pressure"] = (close - low) / denom
    df["buying_pressure"] = df["buying_pressure"].fillna(0.5)

    df["sin_day"] = np.sin(2 * np.pi * df["timestamp"].dt.dayofweek / 7)
    df["cos_day"] = np.cos(2 * np.pi * df["timestamp"].dt.dayofweek / 7)
    df["sin_month"] = np.sin(2 * np.pi * df["timestamp"].dt.month / 12)
    df["cos_month"] = np.cos(2 * np.pi * df["timestamp"].dt.month / 12)

    return df


def build_feature_frame(
    candles_df: pd.DataFrame,
    fgi_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    df = candles_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)

    df = add_base_features(df)
    df = add_tech_features(df)

    if fgi_df is not None and len(fgi_df) > 0:
        fgi = fgi_df.copy()
        fgi["timestamp"] = pd.to_datetime(fgi["timestamp"], utc=True).dt.floor("D")
        fgi = fgi.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp")
        df = df.merge(fgi[["timestamp", "fgi", "fgi_norm"]], on="timestamp", how="left")

    return df


def filter_feature_set(df: pd.DataFrame, feature_set: str) -> pd.DataFrame:
    base_cols = ["timestamp", "open", "high", "low", "close", "volume", "log_close", "log_return", "log_volume"]
    tech_extra_cols = [
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
    ]

    if feature_set == "tech":
        cols = base_cols + tech_extra_cols
        required_cols = ["timestamp", "open", "high", "low", "close", "volume", "log_return", "rsi_14", "sma_100", "ema_100", "volatility_30"]
    else:
        macro_cols = [
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
        ]
        cols = base_cols + tech_extra_cols + macro_cols + ["fgi", "fgi_norm"]
        required_cols = [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "log_return",
            "rsi_14",
            "sma_100",
            "ema_100",
            "volatility_30",
            "fgi",
        ]
        required_cols += [c for c in macro_cols if c in df.columns]

    df2 = df[[c for c in cols if c in df.columns]].copy()
    df2 = df2.dropna(subset=required_cols).reset_index(drop=True)
    return df2
