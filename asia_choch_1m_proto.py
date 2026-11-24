"""Prototype: Asia sweep -> CHoCH -> first FVG, 1m EURUSD.

Uses smartmoneyconcepts for sessions, swings, CHoCH and FVG.
"""
from __future__ import annotations

import hashlib
import os
import time
from collections import Counter

import numpy as np
import pandas as pd
from smartmoneyconcepts import smc

PAIR = "EURUSD"
PATH = "aqua/cache/eurusd_m1_clean.parquet"
START = os.environ.get("ASIA_START", "2024-11-17")
END = os.environ.get("ASIA_END", "2026-11-18")
PIP = 0.0001
MAX_PEN_PIPS = 10.0
MAX_BARS_TO_CHOCH = 30
SWING_LENGTH = 2
CHOCH_WINDOW = 180
MAX_FVG_WAIT = 10
ENTRY_EXPIRY_BARS = 30
STOP_BUFFER_PIPS = 0.0
MIN_RISK_PIPS = 1.0


def load() -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    df = pd.read_parquet(PATH, columns=["dt", "open", "high", "low", "close"])
    dt = pd.to_datetime(df["dt"], utc=True)
    keep = (dt >= pd.Timestamp(START, tz="UTC")) & (dt < pd.Timestamp(END, tz="UTC"))
    df = df.loc[keep, ["open", "high", "low", "close"]].reset_index(drop=True)
    dt = dt[keep].reset_index(drop=True)
    return df, pd.DatetimeIndex(dt.dt.tz_convert("America/New_York"))


def asia_sessions(df: pd.DataFrame, ny: pd.DatetimeIndex):
    mins = ny.hour * 60 + ny.minute
    mask = mins >= 20 * 60
    dates = ny.normalize()
    out = []
    for date in pd.unique(dates[mask]):
        idx = np.flatnonzero(mask & (dates == date))
        if len(idx) < 60:
            continue
        sl = df.iloc[idx].copy()
        sl.index = ny[idx]
        s = smc.sessions(sl, "Custom", "20:00", "00:00", time_zone="UTC")
        high = float(s["High"].iloc[-1])
        low = float(s["Low"].iloc[-1])
        if high <= low:
            continue
        day = pd.Timestamp(date)
        if day.tz is None:
            day = day.tz_localize(ny.tz)
        end = int(ny.searchsorted(day))
        cutoff = int(ny.searchsorted(day + pd.Timedelta(hours=16)))
        if end >= len(df):
            continue
        out.append(dict(date=day.date(), high=high, low=low,
                        start=end, stop=min(cutoff, len(df))))
    return out


def choch_at(df: pd.DataFrame, i: int, direction: str):
    lo = max(0, i - CHOCH_WINDOW + 1)
    w = df.iloc[lo:i + 1].reset_index(drop=True)
    sw = smc.swing_highs_lows(w, SWING_LENGTH)
    bc = smc.bos_choch(w, sw, close_break=True)
    want = 1 if direction == "long" else -1
    last = len(w) - 1
    hits = bc[(bc["CHOCH"] == want) & (bc["BrokenIndex"] == last)]
    if len(hits) == 0:
        return None
    row = hits.index[-1]
    return dict(level=float(bc.loc[row, "Level"]), signal=int(row))


def detect(df: pd.DataFrame, ny: pd.DatetimeIndex):
    n = len(df)
    gaps = smc.fvg(df, join_consecutive=False)
    sessions = asia_sessions(df, ny)
    C = Counter()
    setups = []
    C["sessions"] = len(sessions)
    t0 = time.time()
    for si, sess in enumerate(sessions):
        active = {}
        for i in range(sess["start"], sess["stop"]):
            hi, lo, cl = float(df.high[i]), float(df.low[i]), float(df.close[i])
            # high sweep -> short
            if "short" not in active:
                if hi > sess["high"]:
                    if cl >= sess["high"]:
                        C["breakout_high"] += 1
                    elif (hi - sess["high"]) / PIP > MAX_PEN_PIPS:
                        C["pen_too_large_high"] += 1
                    else:
                        C["sweep_high"] += 1
                        active["short"] = dict(direction="short", sweep_bar=i,
                                               extreme=hi, level=sess["high"])
            # low sweep -> long
            if "long" not in active:
                if lo < sess["low"]:
                    if cl <= sess["low"]:
                        C["breakout_low"] += 1
                    elif (sess["low"] - lo) / PIP > MAX_PEN_PIPS:
                        C["pen_too_large_low"] += 1
                    else:
                        C["sweep_low"] += 1
                        active["long"] = dict(direction="long", sweep_bar=i,
                                              extreme=lo, level=sess["low"])
            for direction in list(active):
                cand = active[direction]
                if i <= cand["sweep_bar"]:
                    continue
                if i - cand["sweep_bar"] > MAX_BARS_TO_CHOCH:
                    C[f"expired_{direction}"] += 1
                    del active[direction]
                    continue
                ch = choch_at(df, i, direction)
                if ch is None:
                    continue
                C[f"choch_{direction}"] += 1
                del active[direction]
                # first FVG after CHoCH confirmation
                made = False
                for i3 in range(i + 1, min(i + 1 + MAX_FVG_WAIT, n - 1)):
                    f = gaps.iloc[i3]
                    if not np.isfinite(f["FVG"]) or int(f["FVG"]) != (1 if direction == "long" else -1):
                        continue
                    top, bottom = float(f["Top"]), float(f["Bottom"])
                    c3 = float(df.close[i3])
                    if direction == "long":
                        if c3 <= top:
                            continue
                        entry = top
                        stop = cand["extreme"] - STOP_BUFFER_PIPS * PIP
                        target = sess["high"]
                        ok = target > entry and stop < entry
                    else:
                        if c3 >= bottom:
                            continue
                        entry = bottom
                        stop = cand["extreme"] + STOP_BUFFER_PIPS * PIP
                        target = sess["low"]
                        ok = target < entry and stop > entry
                    risk = abs(entry - stop)
                    if not ok or risk / PIP < MIN_RISK_PIPS:
                        continue
                    C["setups"] += 1
                    sid = hashlib.md5(
                        f"{sess['date']}{direction}{cand['sweep_bar']}{i}{i3}".encode()
                    ).hexdigest()[:12]
                    setups.append(dict(
                        setup_id=sid, pair=PAIR, direction=direction,
                        session_date=str(sess["date"]), sweep_bar=int(cand["sweep_bar"]),
                        sweep_ts=int(df.index[i] if False else 0),
                        sweep_level=float(cand["level"]), sweep_extreme=float(cand["extreme"]),
                        choch_bar=int(i), fvg_bar=int(i3),
                        fvg_top=top, fvg_bottom=bottom,
                        entry_limit=float(entry), stop=float(stop), target=float(target),
                        dol_price=float(target),
                        risk=float(risk), rr=float(abs(target - entry) / risk),
                        created_bar=int(i3), expiry_bar=int(i3 + ENTRY_EXPIRY_BARS),
                        cycle=0,
                    ))
                    made = True
                    break
                if not made:
                    C["no_valid_fvg"] += 1
        if (si + 1) % 100 == 0:
            print(f"  sessions {si+1}/{len(sessions)} setups {len(setups)} "
                  f"{time.time()-t0:.1f}s", flush=True)
    C["elapsed_s"] = round(time.time() - t0, 1)
    return setups, C


if __name__ == "__main__":
    df, ny = load()
    print(f"bars {len(df):,} {ny[0]} .. {ny[-1]}", flush=True)
    setups, C = detect(df, ny)
    print(C)
    for s in setups[:5]:
        print({k: s[k] for k in ("session_date", "direction", "sweep_bar",
                                  "choch_bar", "fvg_bar", "entry_limit",
                                  "stop", "target", "rr")})
