"""Run the Asia sweep -> CHoCH -> first FVG strategy on 1m EURUSD."""
from __future__ import annotations

import copy
import json
import os
import sys
from collections import Counter

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
from strategies.ict_baseline.report import trade_stats

OUT = os.environ.get("ASIA_OUT", "data/scratch/asia_choch_1m")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    df, ny = proto.load()
    print(f"bars {len(df):,} {ny[0]} .. {ny[-1]}", flush=True)
    setups, counters = proto.detect(df, ny)
    print("detection", dict(counters), flush=True)

    # The prototype used the CHoCH close for the gap check. Re-apply the
    # stricter C3-close check without rerunning detection.
    kept = []
    for s in setups:
        c3 = float(df.close[s["fvg_bar"]])
        if s["direction"] == "long" and c3 <= s["fvg_top"]:
            counters["gap_already_filled"] += 1
            continue
        if s["direction"] == "short" and c3 >= s["fvg_bottom"]:
            counters["gap_already_filled"] += 1
            continue
        kept.append(s)
    setups = kept
    print(f"setups after C3 filter: {len(setups)}", flush=True)

    for s in setups:
        s["dol_price"] = s["target"]
        s["sweep_ts"] = int(pd.Timestamp(ny[s["sweep_bar"]]).timestamp())
        s["choch_ts"] = int(pd.Timestamp(ny[s["choch_bar"]]).timestamp())
        s["created_ts"] = int(pd.Timestamp(ny[s["created_bar"]]).timestamp())
        s["session_high"] = float(s["target"] if s["direction"] == "long"
                                 else s["sweep_level"])
        s["session_low"] = float(s["sweep_level"] if s["direction"] == "long"
                                else s["target"])

    # Persist detection before simulation so a later failure cannot lose 13
    # minutes of CHoCH scanning.
    pd.DataFrame(setups).to_csv(os.path.join(OUT, "setups.csv"), index=False)
    with open(os.path.join(OUT, "counters.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(counters), fh, indent=2, sort_keys=True, default=str)
    if not setups:
        print("no setups", flush=True)
        return 0

    cfg = copy.deepcopy(base_config.DEFAULTS)
    cfg["time"]["entry_windows_ny"] = [["00:00", "16:00"]]
    cfg["time"]["session_cutoff_ny"] = "16:00"
    cfg["risk"]["max_hold_bars"] = 1440
    cfg["risk"]["stop_loss_cap_r"] = 1.05
    cfg["risk"]["max_trades_per_day"] = 2
    cfg["costs"]["spread_pips"] = 1.0
    cfg["costs"]["slippage_pips"] = 0.2
    cfg["costs"]["commission_pips"] = 0.0
    cfg["news"]["enabled"] = False

    sim = None
    # simulate needs a Bars-like object; build one from the 1m frame.
    from strategies.ict_baseline.data import Bars, average_true_range
    utc = pd.DatetimeIndex(ny).tz_convert("UTC")
    ts = (utc.view("int64") // 10**6).astype("int64")
    atr = average_true_range(df.high.to_numpy(float), df.low.to_numpy(float),
                             df.close.to_numpy(float), 14)
    bars = Bars(ts=ts, dt=utc, ny=pd.DatetimeIndex(ny),
                o=df.open.to_numpy(float), h=df.high.to_numpy(float),
                l=df.low.to_numpy(float), c=df.close.to_numpy(float), atr=atr)

    sim = simulate(proto.PAIR, bars, setups, cfg)
    trades = sim.trades
    stats = trade_stats(trades)
    counters.update(sim.fills)
    counters["trades"] = len(trades)

    pd.DataFrame(setups).to_csv(os.path.join(OUT, "setups.csv"), index=False)
    pd.DataFrame(trades).to_csv(os.path.join(OUT, "trades.csv"), index=False)
    with open(os.path.join(OUT, "counters.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(counters), fh, indent=2, sort_keys=True, default=str)

    lines = ["# Asia sweep -> CHoCH -> first FVG, 1m EURUSD", "",
             f"Window: {ny[0].date()} .. {ny[-1].date()}", "",
             "## Detection funnel", ""]
    for k, v in counters.items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Trade statistics", ""]
    for k, v in stats.items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Exit reasons", ""]
    exits = Counter(t["exit_reason"] for t in trades)
    for k, v in exits.most_common():
        lines.append(f"- {k}: {v}")
    if trades:
        net = np.array([t["net_r"] for t in trades])
        lines += ["", "## Gross / cost", "",
                  f"- gross_r: {round(float(net.sum() + sum(t['cost_r'] for t in trades)), 2)}",
                  f"- cost_r: {round(float(sum(t['cost_r'] for t in trades)), 2)}",
                  f"- avg_risk_pips: {round(float(np.mean([t['risk_pips'] for t in trades])), 2)}",
                  f"- avg_rr: {round(float(np.mean([s['rr'] for s in setups])), 3)}"]
        lines += ["", "## By year", ""]
        d = pd.DataFrame(trades)
        d["year"] = pd.to_datetime(d.entry_ts, unit="s", utc=True).dt.tz_convert(
            "America/New_York").dt.year
        y = d.groupby("year").net_r.agg(["size", "mean", "sum"]).round(3)
        lines += ["| year | n | mean R | sum R |", "|---:|---:|---:|---:|"]
        for year, row in y.iterrows():
            lines.append(f"| {year} | {int(row['size'])} | {row['mean']} | {row['sum']} |")
        lines += ["", "## By direction", ""]
        lines += ["| direction | n | mean R | sum R |", "|---|---:|---:|---:|"]
        for direction, g in d.groupby("direction"):
            lines.append(f"| {direction} | {len(g)} | {round(g.net_r.mean(), 3)} | {round(g.net_r.sum(), 2)} |")
    with open(os.path.join(OUT, "report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"report: {os.path.abspath(OUT)}", flush=True)
    print(stats, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
