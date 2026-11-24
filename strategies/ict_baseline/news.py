"""News blackout filter. Implemented, disabled by default.

The baseline has no economic calendar in the repository, so the filter reads a
CSV the caller supplies. Format, one row per event:

    ts,currency,impact
    2024-01-05T13:30:00Z,USD,high

ts is ISO-8601 UTC or epoch milliseconds. currency is optional; when present it
must match one of the pair's currencies for the event to block.

enabled=false makes every function here a no-op, which is the shipped state.
"""
from __future__ import annotations

import csv
import os

import numpy as np
import pandas as pd


def _event_times(path: str) -> list[tuple]:
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            stamp = str(row.get("ts", "")).strip()
            if not stamp:
                continue
            rows.append((stamp, str(row.get("currency", "")).strip().upper(),
                         str(row.get("impact", "")).strip().lower()))
    if not rows:
        return []
    parsed = []
    for stamp, currency, impact in rows:
        try:
            value = float(stamp)
        except ValueError:
            value = pd.Timestamp(stamp)
            value = value.tz_localize("UTC") if value.tzinfo is None else value
            value = value.tz_convert("UTC")
        else:
            value = pd.Timestamp(int(value), unit="ms", tz="UTC")
        parsed.append((value, currency, impact))
    return parsed


def blackout_mask(pair: str, bars, cfg: dict) -> np.ndarray:
    """True on bars inside a configured blackout window."""
    news = cfg.get("news", {})
    mask = np.zeros(len(bars), dtype=bool)
    if not bool(news.get("enabled", False)):
        return mask
    path = news.get("csv")
    if not path:
        raise ValueError("news.enabled is true but news.csv is not set")
    path = path if os.path.isabs(path) else os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), path)
    before = pd.Timedelta(minutes=int(news.get("before_minutes", 30)))
    after = pd.Timedelta(minutes=int(news.get("after_minutes", 30)))
    wanted = {pair[:3].upper(), pair[3:6].upper()}
    for event_ts, currency, impact in _event_times(path):
        if currency and currency not in wanted:
            continue
        if impact and impact not in set(news.get("impacts", ["high"])):
            continue
        lo = event_ts - before
        hi = event_ts + after
        mask |= (bars.dt >= lo) & (bars.dt <= hi)
    return mask
