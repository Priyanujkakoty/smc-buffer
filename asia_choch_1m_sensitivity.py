"""Sensitivity checks on saved 1m Asia sweep setups."""
from __future__ import annotations

import copy
import math
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asia_choch_1m_proto as proto
from strategies.ict_baseline import config as base_config
from strategies.ict_baseline.backtest import simulate
from strategies.ict_baseline.data import Bars, average_true_range
from strategies.ict_baseline.report import trade_stats

OUT = "data/scratch/asia_choch_1m"
PIP = 0.0001


def bars_from_proto():
    df, ny = proto.load()
    utc = pd.DatetimeIndex(ny).tz_convert("UTC")
    ts = (utc.view("int64") // 10**6).astype("int64")
    atr = average_true_range(df.high.to_numpy(float), df.low.to_numpy(float),
                             df.close.to_numpy(float), 14)
    return df, Bars(ts=ts, dt=utc, ny=pd.DatetimeIndex(ny),
                    o=df.open.to_numpy(float), h=df.high.to_numpy(float),
                    l=df.low.to_numpy(float), c=df.close.to_numpy(float), atr=atr)


def run(setups, bars, stop_buffer=0.0, expiry=30, max_hold=1440):
    orders = copy.deepcopy(setups)
    for s in orders:
        if stop_buffer:
            if s["direction"] == "long":
                s["stop"] = s["stop"] - stop_buffer * PIP
            else:
                s["stop"] = s["stop"] + stop_buffer * PIP
            s["risk"] = abs(s["entry_limit"] - s["stop"])
        s["expiry_bar"] = int(s["created_bar"] + expiry)
    cfg = copy.deepcopy(base_config.DEFAULTS)
    cfg["time"]["entry_windows_ny"] = [["00:00", "16:00"]]
    cfg["time"]["session_cutoff_ny"] = "16:00"
    cfg["risk"]["max_hold_bars"] = max_hold
    cfg["risk"]["max_trades_per_day"] = 2
    cfg["costs"]["spread_pips"] = 1.0
    cfg["costs"]["slippage_pips"] = 0.2
    cfg["costs"]["commission_pips"] = 0.0
    cfg["news"]["enabled"] = False
    sim = simulate("EURUSD", bars, orders, cfg)
    st = trade_stats(sim.trades)
    if not st.get("n"):
        return st, sim
    r = np.array([t["net_r"] for t in sim.trades])
    st["t"] = round(float(r.mean() / (r.std(ddof=1) / math.sqrt(len(r)))), 2)
    return st, sim


def main():
    df, bars = bars_from_proto()
    setups = pd.read_csv(os.path.join(OUT, "setups.csv")).to_dict("records")
    for s in setups:
        for k in ("created_bar", "expiry_bar", "cycle", "sweep_bar", "choch_bar",
                  "fvg_bar"):
            if k in s and pd.notna(s[k]):
                s[k] = int(s[k])
    print("setups", len(setups))
    rows = []
    for buffer in (0.0, 0.5, 1.0, 2.0):
        for expiry in (15, 30, 60):
            st, _ = run(setups, bars, stop_buffer=buffer, expiry=expiry)
            rows.append(dict(buffer=buffer, expiry=expiry, **st))
            print(f"buffer {buffer} expiry {expiry}: {st}", flush=True)
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT, "sensitivity.csv"), index=False)
    print(out[["buffer", "expiry", "n", "win_rate", "avg_r", "total_r",
               "profit_factor", "max_drawdown_r", "t"]].to_string(index=False))


if __name__ == "__main__":
    main()
