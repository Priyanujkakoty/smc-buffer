"""Weekly bias, prior-week dealing range, and the equilibrium veto.

Bias rule (baseline, stated, not inferred): the direction is the sign of
close minus open of the last FULLY CLOSED weekly candle. The candle is closed
only when its Monday 00:00 NY end boundary has passed. The bias is frozen for
the following week and cannot be changed by the forming candle.

Weeks are bucketed on naive New York wall-clock dates, then converted to UTC.
Adding a timedelta to a tz-aware stamp adds absolute hours, which would shift a
bucket by an hour across a DST change; wall-clock bucketing avoids that.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .timecycle import wall_to_utc, week_start_wall


@dataclass
class WeeklyTable:
    start_ts: np.ndarray   # epoch ms, Monday 00:00 NY -> UTC
    end_ts: np.ndarray     # epoch ms, next Monday 00:00 NY -> UTC
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    bars: np.ndarray
    direction: np.ndarray  # +1 bullish, -1 bearish, 0 flat
    complete: np.ndarray


def build_weekly(bars, min_bars: int = 400) -> WeeklyTable:
    wall = week_start_wall(bars.ny)
    frame = pd.DataFrame({
        "week": wall,
        "open": bars.o, "high": bars.h, "low": bars.l, "close": bars.c,
    })
    agg = frame.groupby("week", sort=True).agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"), bars=("close", "size"))
    week_start = pd.DatetimeIndex(agg.index)
    week_end = week_start + pd.Timedelta(days=7)

    market_tz = str(bars.ny.tz)
    start_utc = wall_to_utc(week_start, market_tz)
    end_utc = wall_to_utc(week_end, market_tz)
    last_ts = int(bars.ts[-1]) if len(bars) else 0

    end_ts = (end_utc.view("int64") // 10 ** 6).astype("int64")
    start_ts = (start_utc.view("int64") // 10 ** 6).astype("int64")
    direction = np.sign(agg["close"].to_numpy() - agg["open"].to_numpy())
    direction = direction.astype(np.int64)
    complete = ((agg["bars"].to_numpy() >= min_bars)
                & (end_ts <= last_ts))
    return WeeklyTable(start_ts=start_ts, end_ts=end_ts,
                       open=agg["open"].to_numpy(dtype=float),
                       high=agg["high"].to_numpy(dtype=float),
                       low=agg["low"].to_numpy(dtype=float),
                       close=agg["close"].to_numpy(dtype=float),
                       bars=agg["bars"].to_numpy(dtype=np.int64),
                       direction=direction, complete=complete)


def bias_series(bars, weekly: WeeklyTable) -> dict:
    """Per-bar bias, week anchor and prior-week range for the whole file."""
    n = len(bars)
    bias = np.zeros(n, dtype=np.int64)
    week_id = np.full(n, -1, dtype=np.int64)
    range_high = np.full(n, np.nan)
    range_low = np.full(n, np.nan)

    ends = weekly.end_ts
    raw = np.searchsorted(ends, bars.ts, side="right") - 1
    # Map every row to the newest COMPLETE week at or before it.
    last_complete = np.full(len(ends), -1, dtype=np.int64)
    running = -1
    for j in range(len(ends)):
        if weekly.complete[j]:
            running = j
        last_complete[j] = running
    pos = np.where(raw >= 0, last_complete[np.clip(raw, 0, None)], -1)
    pos = np.where(raw < 0, -1, pos)
    week_id[:] = pos
    ok = pos >= 0
    bias[ok] = weekly.direction[pos[ok]]
    range_high[ok] = weekly.high[pos[ok]]
    range_low[ok] = weekly.low[pos[ok]]
    return dict(bias=bias, week_id=week_id, range_high=range_high,
                range_low=range_low)


def equilibrium(range_high: float, range_low: float, atr: float,
                band_atr: float = 0.25) -> dict:
    """50% of the dealing range plus an ATR band. Anchors are returned."""
    mid = 0.5 * (range_high + range_low)
    band = float(band_atr) * float(atr)
    return dict(mid=mid, band=band, low=mid - band, high=mid + band,
                range_high=range_high, range_low=range_low)


def in_equilibrium(price: float, zone: dict) -> bool:
    return zone["low"] <= price <= zone["high"]
