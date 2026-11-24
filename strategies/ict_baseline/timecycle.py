"""Session, day and 90-minute cycle helpers. DST is handled by tz_convert.

Weekly buckets are built from *naive* New York wall-clock dates so a DST change
inside a week cannot shift the bucket boundary by an hour.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _hm(text: str) -> int:
    hh, mm = str(text).split(":")
    return int(hh) * 60 + int(mm)


def minutes_of_day(ny: pd.DatetimeIndex) -> np.ndarray:
    return (ny.hour * 60 + ny.minute).to_numpy(dtype=np.int64)


def in_windows(ny: pd.DatetimeIndex, windows) -> np.ndarray:
    """True where local NY time is inside any [start, end) window."""
    mins = minutes_of_day(ny)
    mask = np.zeros(len(ny), dtype=bool)
    for start, end in windows:
        mask |= (mins >= _hm(start)) & (mins < _hm(end))
    return mask


def session_mask(ny: pd.DatetimeIndex, start: str, end: str) -> np.ndarray:
    """True inside one session, including a session that crosses midnight."""
    mins = minutes_of_day(ny)
    a, b = _hm(start), _hm(end)
    if a < b:
        return (mins >= a) & (mins < b)
    return (mins >= a) | (mins < b)


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Contiguous [start, end) runs of True in bar order."""
    if len(mask) == 0:
        return []
    padded = np.r_[False, mask, False].astype(np.int8)
    edges = np.flatnonzero(np.diff(padded))
    return [(int(a), int(b)) for a, b in zip(edges[::2], edges[1::2])]


def day_key(ny: pd.DatetimeIndex) -> np.ndarray:
    """NY calendar date as int YYYYMMDD."""
    return (ny.year * 10000 + ny.month * 100 + ny.day).to_numpy(dtype=np.int64)


def cycle_index(ny: pd.DatetimeIndex, anchor_minutes: int = 0,
                length_minutes: int = 90) -> np.ndarray:
    """Cycle number within the NY day. Anchor 00:00 by default.

    00:00 -> 0, 01:29 -> 0, 01:30 -> 1. Context only, never an entry trigger.
    """
    mins = minutes_of_day(ny) - int(anchor_minutes)
    mins = np.where(mins < 0, mins + 24 * 60, mins)
    return (mins // int(length_minutes)).astype(np.int64)


def week_start_wall(ny: pd.DatetimeIndex) -> pd.Series:
    """Naive Monday 00:00 local for each bar. weekday: Monday == 0."""
    naive = ny.tz_localize(None)
    midnight = naive.normalize()
    return midnight - pd.to_timedelta(midnight.day_of_week, unit="D")


def wall_to_utc(wall: pd.DatetimeIndex, market_tz: str) -> pd.DatetimeIndex:
    return wall.tz_localize(market_tz).tz_convert("UTC")


def day_start_utc(ny: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return ny.normalize().tz_convert("UTC")


def next_day_start_utc(ny: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return (ny.normalize() + pd.Timedelta(days=1)).tz_convert("UTC")
