"""Sweep risk vs challenge pass rate and time-to-pass. Quick answer run."""
import os
import sys

os.environ.setdefault("ASIA_START", "2021-01-01")
os.environ.setdefault("ASIA_END", "2026-11-18")
os.environ.setdefault("ASIA_OUT", "data/scratch/asia_choch_1m_2021")
sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("data/scratch"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import asia_choch_1m_moneycheck as mc  # noqa: E402

df = mc.load_trades()
blk = mc.blocks(df)
hist = mc.history(df)
dd_r = hist["max_dd_r"]
day_r = -hist["worst_day_r"]

rows = []
risks = [0.01, 0.0125, 0.015, 0.0175, 0.02, 0.025, 0.03, 0.04, 0.05]
for risk in risks:
    d = mc.run_grid(blk, risk, npaths=20000, horizon=730, single=True)
    ok = d.funded == 1
    pd_ = d.loc[ok, "pass_day"]
    rows.append({
        "risk": risk * 100,
        "challenge": ok.mean(),
        "median_days": pd_.median() if ok.any() else np.nan,
        "p90_days": pd_.quantile(0.9) if ok.any() else np.nan,
        "share_90d": (pd_ <= 90).sum() / len(d),
        "share_180d": (pd_ <= 180).sum() / len(d),
        "share_365d": (pd_ <= 365).sum() / len(d),
        "days_to_80pct_median": pd_.quantile(0.2) if ok.any() else np.nan,
        "daily_breach": (d.breach_type == 1).mean(),
        "dd_breach": (d.breach_type == 2).mean(),
        "hist_dd_mult": dd_r * risk * 5000 / 500.0,
        "hist_day_mult": day_r * risk * 5000 / 250.0,
    })
    print(rows[-1], flush=True)

out = pd.DataFrame(rows)
print()
print(out.to_string(index=False, float_format=lambda v: f"{v:.4g}"))
