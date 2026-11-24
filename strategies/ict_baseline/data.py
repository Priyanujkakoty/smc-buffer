"""Bar loading, resampling and ATR. All timestamps are int64 epoch ms UTC."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Bars:
    """Execution-timeframe bars plus derived fields.

    ts      epoch ms, bar OPEN time, UTC
    dt      tz-aware UTC index, bar open
    ny      same instants in America/New_York (entry windows, cycles, days)
    o/h/l/c float64 OHLC
    atr     float64 ATR, NaN until the period is filled
    """

    ts: np.ndarray
    dt: pd.DatetimeIndex
    ny: pd.DatetimeIndex
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    atr: np.ndarray

    def __len__(self) -> int:
        return len(self.ts)

    @classmethod
    def from_ohlc(cls, o, h, l, c, start="2024-01-01", minutes=15,
                  atr_period=14, market_tz="America/New_York"):
        """Build synthetic bars for tests. ATR falls back to bar range."""
        o = np.asarray(o, dtype=float)
        h = np.asarray(h, dtype=float)
        l = np.asarray(l, dtype=float)
        c = np.asarray(c, dtype=float)
        n = len(o)
        dt = pd.date_range(start=start, periods=n, freq=f"{minutes}min", tz="UTC")
        ts = (dt.view("int64") // 10 ** 6).astype("int64")
        atr = average_true_range(h, l, c, atr_period)
        atr = np.where(np.isnan(atr), h - l, atr)
        return cls(ts=ts, dt=dt, ny=dt.tz_convert(market_tz),
                   o=o, h=h, l=l, c=c, atr=atr)


def average_true_range(h: np.ndarray, l: np.ndarray, c: np.ndarray,
                       period: int) -> np.ndarray:
    prev = np.empty_like(c)
    prev[0] = c[0]
    prev[1:] = c[:-1]
    tr = np.maximum.reduce([h - l, np.abs(h - prev), np.abs(l - prev)])
    out = np.full(len(c), np.nan)
    if period <= 1:
        out[:] = tr
        return out
    if len(c) >= period:
        kernel = np.ones(period) / period
        out[period - 1:] = np.convolve(tr, kernel, mode="valid")
    return out


def load_pair(path: str, cfg: dict) -> Bars:
    """Load one *_5m_clean.parquet and resample to the execution timeframe.

    A resampled bar is kept only when it contains a full set of base bars, so
    the tail of the file cannot introduce a partial candle.
    """
    df = pd.read_parquet(path)
    if "dt" in df.columns:
        idx = pd.DatetimeIndex(pd.to_datetime(df["dt"], utc=True))
    else:
        idx = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    frame = pd.DataFrame({
        "open": df["open"].astype(float).to_numpy(),
        "high": df["high"].astype(float).to_numpy(),
        "low": df["low"].astype(float).to_numpy(),
        "close": df["close"].astype(float).to_numpy(),
    }, index=idx).sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]

    base = int(cfg["data"]["base_minutes"])
    execution = int(cfg["data"]["execution_minutes"])
    rule = f"{execution}min"
    agg = frame.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"})
    counts = frame["close"].resample(rule, label="left", closed="left").count()
    agg = agg[counts >= execution // base]
    agg = agg.dropna()

    start = cfg["data"].get("start")
    end = cfg["data"].get("end")
    if start:
        agg = agg[agg.index >= pd.Timestamp(start, tz="UTC")]
    if end:
        agg = agg[agg.index <= pd.Timestamp(end, tz="UTC")]

    idx = pd.DatetimeIndex(agg.index)
    ts = (idx.view("int64") // 10 ** 6).astype("int64")
    h = agg["high"].to_numpy(dtype=float)
    l = agg["low"].to_numpy(dtype=float)
    c = agg["close"].to_numpy(dtype=float)
    atr = average_true_range(h, l, c, int(cfg["structure"]["atr_period"]))
    return Bars(ts=ts, dt=idx, ny=idx.tz_convert(cfg["time"]["market_tz"]),
                o=agg["open"].to_numpy(dtype=float), h=h, l=l, c=c, atr=atr)


def pip_size(pair: str) -> float:
    return 0.01 if "JPY" in pair.upper() else 0.0001
