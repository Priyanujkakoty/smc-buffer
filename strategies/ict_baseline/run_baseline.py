"""CLI entry point for the deterministic ICT baseline.

Run from the repository root:

    python -m strategies.ict_baseline.run_baseline --pairs EURUSD GBPUSD

No optimisation happens here. One pass, one config, one report.
"""
from __future__ import annotations

import argparse
import glob as gl
import os
import sys
from collections import Counter

from . import config as config_mod
from .backtest import simulate
from .data import load_pair
from .report import write_report
from .setup import run_pair

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def resolve(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


def find_pair_path(pattern: str, pair: str) -> str | None:
    folder = os.path.dirname(resolve(pattern))
    prefix = pair.lower() + "_"
    hits = [p for p in gl.glob(os.path.join(folder, "*_5m_clean.parquet"))
            if os.path.basename(p).lower().startswith(prefix)]
    return sorted(hits)[0] if hits else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None)
    parser.add_argument("--out", default="data/scratch/ict_baseline")
    parser.add_argument("--pairs", nargs="*", default=None)
    parser.add_argument("--start", default=None, help="UTC date, inclusive")
    parser.add_argument("--end", default=None, help="UTC date, inclusive")
    args = parser.parse_args(argv)

    cfg = config_mod.load(args.config)
    if args.start:
        cfg["data"]["start"] = args.start
    if args.end:
        cfg["data"]["end"] = args.end
    warnings = config_mod.validate(cfg)
    for warning in warnings:
        print(f"[config] {warning}", file=sys.stderr)
    fingerprint = config_mod.fingerprint(cfg)
    pairs = args.pairs or list(cfg["data"]["pairs"])
    pattern = cfg["data"]["glob"]

    counters = Counter()
    events: list[dict] = []
    setups: list[dict] = []
    trades: list[dict] = []
    fills = Counter()
    per_pair: dict[str, dict] = {}

    for pair in pairs:
        path = find_pair_path(pattern, pair)
        if path is None:
            print(f"[skip] no data file for {pair}", file=sys.stderr)
            continue
        bars = load_pair(path, cfg)
        if len(bars) == 0:
            print(f"[skip] no bars for {pair}", file=sys.stderr)
            continue
        engine = run_pair(pair, bars, cfg)
        sim = simulate(pair, bars, engine.setups, cfg)
        counters.update(engine.counters)
        counters.update(sim.fills)
        events.extend(engine.events)
        setups.extend(engine.setups)
        trades.extend(sim.trades)
        fills.update(sim.fills)
        net_r = round(sum(t["net_r"] for t in sim.trades), 2)
        per_pair[pair] = dict(bars=len(bars), setups=len(engine.setups),
                              filled=sim.fills.get("filled", 0), net_r=net_r)
        print(f"{pair}: bars {len(bars):,} pools {len(engine.pools):,} "
              f"setups {len(engine.setups)} filled "
              f"{sim.fills.get('filled', 0)} netR {net_r}", flush=True)

    counters["trades"] = len(trades)
    summary = write_report(resolve(args.out), cfg, fingerprint, counters,
                           events, setups, trades, dict(fills), per_pair)
    stats = summary["stats"]
    print(f"\nreport: {resolve(args.out)}")
    if stats.get("n"):
        print(f"trades {stats['n']} | win {stats['win_rate']}% | "
              f"expectancy {stats['avg_r']}R | total {stats['total_r']}R | "
              f"PF {stats['profit_factor']}")
    else:
        print("no trades filled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
