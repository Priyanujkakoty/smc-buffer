"""One-factor sensitivity table for the baseline. Diagnostic only.

This is NOT an optimisation pass. Nothing here is allowed to change the
published baseline. The point is to show which dials the result depends on,
so a later study knows where the fragility is.

    python -m strategies.ict_baseline.ablate --start 2019-01-01 \
        --end 2026-11-01 --out data/scratch/ict_baseline_ablation
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter

from . import config as config_mod
from .backtest import simulate
from .data import load_pair
from .report import trade_stats
from .run_baseline import find_pair_path, resolve
from .setup import run_pair

VARIANTS = [
    ("baseline", {}),
    ("time_stop_48", {"risk": {"max_hold_bars": 48}}),
    ("time_stop_192", {"risk": {"max_hold_bars": 192}}),
    ("time_stop_384", {"risk": {"max_hold_bars": 384}}),
    ("entry_gap_mid", {"fvg": {"entry_fraction": 0.5}}),
    ("entry_gap_far", {"fvg": {"entry_fraction": 1.0}}),
    ("require_large_fvg", {"fvg": {"require_large": True}}),
    ("displacement_0.5atr", {"displacement": {"min_body_atr": 0.5}}),
    ("displacement_1.5atr", {"displacement": {"min_body_atr": 1.5}}),
    ("min_rr_1.5", {"dol": {"min_rr": 1.5}}),
    ("min_rr_3.0", {"dol": {"min_rr": 3.0}}),
    ("equilibrium_off", {"equilibrium": {"veto": False}}),
    ("stop_buffer_0", {"risk": {"stop_buffer_atr": 0.0}}),
    ("stop_buffer_0.25", {"risk": {"stop_buffer_atr": 0.25}}),
    ("mss_lookback_6", {"sweep": {"mss_swing_lookback_bars": 6}}),
    ("mss_lookback_24", {"sweep": {"mss_swing_lookback_bars": 24}}),
    ("mss_window_6", {"sweep": {"max_bars_to_mss": 6}}),
    ("mss_window_24", {"sweep": {"max_bars_to_mss": 24}}),
    ("penetration_0.05atr", {"sweep": {"min_penetration_atr": 0.05}}),
    ("penetration_0.10atr", {"sweep": {"min_penetration_atr": 0.10}}),
]


def run(pairs, start, end, out_dir, cfg_path=None):
    base = config_mod.load(cfg_path)
    if start:
        base["data"]["start"] = start
    if end:
        base["data"]["end"] = end
    pattern = base["data"]["glob"]
    cache: dict[str, object] = {}
    rows = []
    for name, patch in VARIANTS:
        cfg = config_mod._deep_merge(base, patch)
        config_mod.validate(cfg)
        fills: Counter = Counter()
        trades: list[dict] = []
        for pair in pairs:
            key = (pair, cfg["data"]["start"], cfg["data"]["end"],
                   cfg["structure"]["atr_period"])
            if key not in cache:
                path = find_pair_path(pattern, pair)
                cache[key] = load_pair(path, cfg) if path else None
            bars = cache[key]
            if bars is None or len(bars) == 0:
                continue
            engine = run_pair(pair, bars, cfg)
            sim = simulate(pair, bars, engine.setups, cfg)
            trades.extend(sim.trades)
            fills.update(sim.fills)
        stats = trade_stats(trades)
        rows.append(dict(
            variant=name,
            trades=stats.get("n", 0),
            win_rate=stats.get("win_rate", 0.0),
            avg_r=stats.get("avg_r", 0.0),
            total_r=stats.get("total_r", 0.0),
            profit_factor=stats.get("profit_factor"),
            max_dd_r=stats.get("max_drawdown_r", 0.0),
            filled=fills.get("filled", 0),
            expired=fills.get("expired", 0),
            time_exits=sum(1 for t in trades if t["exit_reason"] == "time"),
        ))
        print(f"{name:22s} trades {rows[-1]['trades']:5d} "
              f"win {rows[-1]['win_rate']:5.1f}% "
              f"avgR {rows[-1]['avg_r']:+.4f} "
              f"totalR {rows[-1]['total_r']:+.1f}", flush=True)

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "ablation.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with open(os.path.join(out_dir, "ablation.json"), "w",
              encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2)
        fh.write("\n")
    print(f"\nwrote {path}")
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None)
    parser.add_argument("--out", default="data/scratch/ict_baseline_ablation")
    parser.add_argument("--pairs", nargs="*", default=None)
    parser.add_argument("--start", default="2019-01-01")
    parser.add_argument("--end", default="2026-11-01")
    args = parser.parse_args(argv)
    cfg = config_mod.load(args.config)
    pairs = args.pairs or list(cfg["data"]["pairs"])
    run(pairs, args.start, args.end, resolve(args.out), args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
