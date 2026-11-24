"""Exact headline metrics for the literal and 5-pip-buffer variants."""
from __future__ import annotations

import copy
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from asia_choch_1m_sensitivity import bars_from_proto
import asia_choch_1m_proto as proto
from strategies.ict_baseline import config as base_config
from strategies.ict_baseline.backtest import simulate

OUT = os.environ.get("ASIA_OUT", "data/scratch/asia_choch_1m")
PIP = 0.0001
START = pd.Timestamp(proto.START, tz="UTC")
END = pd.Timestamp(proto.END, tz="UTC")


def run(setups, bars, buffer_pips, cap):
    orders = []
    for s in setups:
        o = dict(s)
        long_side = o["direction"] == "long"
        if buffer_pips:
            o["stop"] = (o["stop"] - buffer_pips * PIP if long_side
                         else o["stop"] + buffer_pips * PIP)
        o["risk"] = abs(o["entry_limit"] - o["stop"])
        o["expiry_bar"] = int(o["created_bar"]) + 30
        orders.append(o)
    cfg = copy.deepcopy(base_config.DEFAULTS)
    cfg["time"]["entry_windows_ny"] = [["00:00", "16:00"]]
    cfg["time"]["session_cutoff_ny"] = "16:00"
    cfg["risk"]["max_hold_bars"] = 1440
    cfg["risk"]["max_trades_per_day"] = 2
    cfg["risk"]["stop_loss_cap_r"] = cap
    cfg["costs"]["spread_pips"] = 1.0
    cfg["costs"]["slippage_pips"] = 0.2
    cfg["costs"]["commission_pips"] = 0.0
    cfg["news"]["enabled"] = False
    return simulate("EURUSD", bars, orders, cfg).trades


def report(trades, label, sessions, calendar_days):
    r = np.array([t["net_r"] for t in trades])
    pips = np.array([(t["exit_price"] - t["entry"]) *
                     (1 if t["direction"] == "long" else -1) / PIP - 1.4
                     for t in trades])
    wins = int((r > 0).sum())
    losses = int((r <= 0).sum())
    gw = float(r[r > 0].sum())
    gl = float(-r[r < 0].sum())
    days = pd.to_datetime([t["entry_ts"] for t in trades], unit="s", utc=True)
    day_keys = days.tz_convert("America/New_York").date
    per_day = pd.Series(1, index=day_keys).groupby(level=0).sum()
    print(f"\n{label}")
    print(f"  trades              {len(r)}")
    print(f"  wins / losses       {wins} / {losses}")
    print(f"  win rate            {wins / len(r) * 100:.4f}%")
    print(f"  EV per trade        {r.mean():+.6f}R  ({pips.mean():+.4f} pips, "
          f"${r.mean() * 25:+.2f} at 0.25% of $10k)")
    print(f"  median trade        {np.median(r):+.6f}R")
    print(f"  SD                  {r.std(ddof=1):.6f}R")
    print(f"  total               {r.sum():+.4f}R  (${r.sum() * 25:+.2f})")
    print(f"  profit factor       {gw / gl:.6f}")
    print(f"  gross win / loss    {gw:.4f}R / {gl:.4f}R")
    print(f"  max drawdown        "
          f"{(np.cumsum(r) - np.maximum.accumulate(np.cumsum(r))).min():.4f}R")
    print(f"  trades/session      {len(r) / sessions:.4f}  ({sessions} sessions)")
    print(f"  trades/calendar day {len(r) / calendar_days:.4f}  "
          f"({calendar_days} days)")
    print(f"  trades/week         {len(r) / (calendar_days / 7):.4f}")
    print(f"  active days         {len(per_day)}")
    print(f"  trades/active day   {per_day.mean():.4f}")
    print(f"  max trades/day      {int(per_day.max())}")
    print(f"  exit mix            "
          f"{dict(pd.Series([t['exit_reason'] for t in trades]).value_counts())}")
    print(f"  capped stops        {sum(1 for t in trades if t.get('capped'))}")


def main():
    _, bars = bars_from_proto()
    raw = pd.read_csv(os.path.join(OUT, "setups.csv")).to_dict("records")
    setups = []
    for s in raw:
        for k in ("created_bar", "expiry_bar", "cycle", "sweep_bar",
                  "choch_bar", "fvg_bar"):
            if k in s and pd.notna(s[k]):
                s[k] = int(s[k])
        setups.append(s)
    orders_ok = max(int(s["created_bar"]) for s in setups) < len(bars.ts)
    if not orders_ok:
        raise SystemExit("setups and bars come from different windows")
    sessions = len({s["session_date"] for s in setups})
    with open(os.path.join(OUT, "counters.json"), encoding="utf-8") as fh:
        sessions = int(json.load(fh)["sessions"])
    calendar_days = (pd.Timestamp(proto.END) - pd.Timestamp(proto.START)).days
    print(f"window {proto.START} .. {proto.END}  sessions {sessions}  "
          f"days {calendar_days}  bars {len(bars.ts):,}", flush=True)
    report(run(setups, bars, 0.0, 1.05), "Literal rules, live cap 1.05R",
           sessions, calendar_days)
    report(run(setups, bars, 5.0, 1.05), "Stop buffer 5 pips, live cap 1.05R",
           sessions, calendar_days)
    report(run(setups, bars, 0.0, None), "Literal rules, no cap (reference)",
           sessions, calendar_days)


if __name__ == "__main__":
    main()
