"""MONEYCHECK - AquaFunded 2 Step Pro, $5k, Asia sweep/CHoCH/FVG buffer-5.

Rules from fx6v2/masters_tests/AQUAFUNDED_RULES_RECON.md (2026-11-15):
  ACCT 5000, P1 +10% (5500), P2 +5% (5250), daily DD 5% ($250, 00:00 UTC),
  max DD 10% ($500) trailing from highest balance incl. floating,
  split 90%, payout processing 3%, consistency best day < 50% of cycle,
  3 qualifying days >= 0.5% ($25) per cycle, 14-day cycles, min payout
  $111.11 gross, eval fee $15 refunded at the 4th payout.

Two payout regimes:
  pay_reset=1  floor resets to the post-withdrawal balance (kernel PR1)
  pay_reset=0  floor stays at HWM-500; only the cushion above the floor is
               withdrawn (conservative, firm text as written)
"""
from __future__ import annotations

import os

os.environ.setdefault("ASIA_START", "2021-01-01")
os.environ.setdefault("ASIA_END", "2026-11-18")
os.environ.setdefault("ASIA_OUT", "data/scratch/asia_choch_1m_2021")

import json
import sys
import time

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (ROOT, os.path.dirname(os.path.abspath(__file__))):
    if p not in sys.path:
        sys.path.insert(0, p)

import asia_choch_1m_exact as ex  # noqa: E402

OUT = os.environ["ASIA_OUT"]
PIP = 0.0001

ACCT = 5000.0
T1 = 5500.0
T2 = 5250.0
DAILY_DD = 250.0
MAX_DD = 500.0
CYCLE = 14
MIN_GROSS = 100.0 / 0.90
SPLIT = 0.90
PROC = 0.03
QUAL_AMT = 25.0
MIN_QUAL = 3
CONSIST = 0.50
EVAL_FEE = 15.0
REFUND_AT = 4


def load_trades() -> pd.DataFrame:
    csv = os.path.join(OUT, "trades_buffer5.csv")
    if os.path.exists(csv):
        return pd.read_csv(csv)
    _, bars = ex.bars_from_proto()
    raw = pd.read_csv(os.path.join(OUT, "setups.csv")).to_dict("records")
    setups = []
    for s in raw:
        for k in ("created_bar", "expiry_bar", "cycle", "sweep_bar",
                  "choch_bar", "fvg_bar"):
            if k in s and pd.notna(s[k]):
                s[k] = int(s[k])
        setups.append(s)
    t = pd.DataFrame(ex.run(setups, bars, 5.0, 1.05))
    t.to_csv(csv, index=False)
    return t


@njit(cache=True)
def sim(block_start, block_len, blk_day, blk_r, nblocks, horizon, risk,
        acct, t1, t2, daily_dd, max_dd, cyc, min_gross, split, proc,
        qual_amt, min_qual, consist, eval_fee, refund_at, pad_r,
        n_weeks, single_attempt, pay_reset, shift_r, week_step):
    bal = acct
    hwm = acct
    floor = acct - max_dd
    stage = 1
    cur_day = -1
    day_pnl = 0.0
    cyc_start = 0
    cyc_profit = 0.0
    cyc_best = 0.0
    cyc_qual = 0
    max_trail = 0.0
    max_daily = 0.0
    payouts = 0
    net_pay = 0.0
    fees = eval_fee
    first_pay = -1
    pass_day = -1
    s1 = 0
    s2 = 0
    funded = 0
    breach_stage = 0
    breach_type = 0
    ntr = 0
    base = 0
    done = False
    rsize = risk * acct
    for w in range(n_weeks):
        if done:
            break
        b = np.random.randint(0, nblocks)
        for j in range(block_start[b], block_start[b] + block_len[b]):
            d = base + blk_day[j]
            if d >= horizon:
                done = True
                break
            if d != cur_day:
                if day_pnl > cyc_best:
                    cyc_best = day_pnl
                if day_pnl >= qual_amt:
                    cyc_qual += 1
                cur_day = d
                day_pnl = 0.0
                if stage == 3 and d >= cyc_start + cyc:
                    gross = cyc_profit
                    if pay_reset == 1:
                        amt = gross
                    else:
                        amt = min(gross, bal - floor - 1.0)
                    ok = (amt >= min_gross and cyc_qual >= min_qual
                          and cyc_best < consist * cyc_profit)
                    if ok:
                        net_pay += amt * split * (1.0 - proc)
                        payouts += 1
                        bal -= amt
                        if pay_reset == 1:
                            hwm = bal
                            floor = bal - max_dd
                        if payouts == refund_at:
                            net_pay += eval_fee
                        if first_pay < 0:
                            first_pay = d
                        cyc_start = d
                        cyc_profit = 0.0
                        cyc_best = 0.0
                        cyc_qual = 0
                    else:
                        cyc_start = d
            pnl = (blk_r[j] + shift_r) * rsize
            ntr += 1
            bal += pnl
            day_pnl += pnl
            if bal > hwm:
                hwm = bal
            floor = hwm - max_dd
            tr = hwm - bal
            if tr > max_trail:
                max_trail = tr
            if day_pnl < max_daily:
                max_daily = day_pnl
            hit_dd = False
            if bal <= floor - pad_r * rsize:
                hit_dd = True
                breach_type = 2
            elif day_pnl <= -daily_dd:
                hit_dd = True
                breach_type = 1
            if hit_dd:
                breach_stage = stage
                if single_attempt:
                    done = True
                    break
                fees += eval_fee
                bal = acct
                hwm = acct
                floor = acct - max_dd
                stage = 1
                cyc_profit = 0.0
                cyc_best = 0.0
                cyc_qual = 0
            if stage == 1 and bal >= t1:
                s1 = 1
                stage = 2
                bal = acct
                hwm = acct
                floor = acct - max_dd
            elif stage == 2 and bal >= t2:
                s2 = 1
                stage = 3
                funded = 1
                pass_day = d
                bal = acct
                hwm = acct
                floor = acct - max_dd
                cyc_start = d
                cyc_profit = 0.0
                cyc_best = 0.0
                cyc_qual = 0
            if stage == 3:
                cyc_profit += pnl
            if single_attempt and payouts >= 1:
                done = True
                break
        base += week_step
    return (breach_stage, breach_type, s1, s2, funded, payouts, net_pay,
            fees, first_pay, max_trail, max_daily, ntr, pass_day)


def blocks(df: pd.DataFrame, block_weeks: int = 1):
    d = pd.to_datetime(df.entry_ts, unit="s", utc=True)
    day = (d.dt.tz_convert("UTC").dt.normalize() - d.min().normalize()).dt.days
    step = 7 * block_weeks
    week = day // step
    starts, lens, bday, br = [], [], [], []
    tmp = df.assign(day=day.values, week=week.values)
    for w, g in tmp.groupby("week"):
        starts.append(len(br))
        lens.append(len(g))
        bday.extend((g.day - w * step).astype(int).tolist())
        br.extend(g.net_r.astype(float).tolist())
    return (np.array(starts, np.int64), np.array(lens, np.int64),
            np.array(bday, np.int64), np.array(br, np.float64))


def run_grid(blk, risk, npaths=50000, horizon=730, single=False, pad=0.0,
             pay_reset=1, shift_r=0.0, seed=20261124, block_weeks=1):
    starts, lens, bday, br = blk
    n_weeks = horizon // (7 * block_weeks) + 1
    np.random.seed(seed)
    cols = np.empty((npaths, 13))
    t0 = time.time()
    for p in range(npaths):
        cols[p] = sim(starts, lens, bday, br, len(starts), horizon, risk,
                      ACCT, T1, T2, DAILY_DD, MAX_DD, CYCLE, MIN_GROSS,
                      SPLIT, PROC, QUAL_AMT, MIN_QUAL, CONSIST, EVAL_FEE,
                      REFUND_AT, pad, n_weeks, single, pay_reset, shift_r,
                      7 * block_weeks)
    names = ["breach_stage", "breach_type", "s1", "s2", "funded", "payouts",
             "net_pay", "fees", "first_pay", "max_trail", "max_daily",
             "ntr", "pass_day"]
    df = pd.DataFrame(cols, columns=names)
    df.attrs["secs"] = time.time() - t0
    return df


def summary(df: pd.DataFrame, label: str, horizon: int, **meta) -> dict:
    pay = df.payouts > 0
    row = {
        "config": label,
        "p1": float(df.s1.mean()),
        "p2_given_p1": float(df.loc[df.s1 == 1, "s2"].mean()) if (df.s1 == 1).any() else 0.0,
        "challenge": float(df.funded.mean()),
        "payout_given_funded": float(pay[df.funded == 1].mean()) if (df.funded == 1).any() else 0.0,
        "survival": float(pay.mean()),
        "breach_p1": float((df.breach_stage == 1).mean()),
        "breach_p2": float((df.breach_stage == 2).mean()),
        "breach_funded": float((df.breach_stage == 3).mean()),
        "daily_breach": float((df.breach_type == 1).mean()),
        "maxdd_breach": float((df.breach_type == 2).mean()),
        "payouts": float(df.payouts.mean()),
        "net_pay": float(df.net_pay.mean()),
        "fees": float(df.fees.mean()),
        "net_cash": float((df.net_pay - df.fees).mean()),
        "median_first_pay": float(df.loc[pay, "first_pay"].median()) if pay.any() else np.nan,
        "p90_first_pay": float(df.loc[pay, "first_pay"].quantile(0.90)) if pay.any() else np.nan,
        "worst_trail": float(df.max_trail.max()),
        "worst_daily": float(df.max_daily.min()),
        "trades": float(df.ntr.mean()),
        "horizon": horizon,
    }
    row.update(meta)
    return row


def history(df: pd.DataFrame) -> dict:
    r = df.net_r.to_numpy(float)
    cum = np.cumsum(r)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    dd = cum - peak
    day = pd.to_datetime(df.entry_ts, unit="s", utc=True).dt.date
    daily = df.groupby(day).net_r.sum()
    idx = pd.to_datetime(df.entry_ts, unit="s", utc=True)
    cyc = pd.Series(r, index=idx).rolling("14D").sum()
    wins = r[r > 0]
    streak = mx = 0
    for v in r < 0:
        streak = streak + 1 if v else 0
        mx = max(mx, streak)
    return {
        "n": int(len(r)),
        "total_r": float(r.sum()),
        "mean_r": float(r.mean()),
        "sd_r": float(r.std(ddof=1)),
        "pf": float(wins.sum() / -r[r < 0].sum()),
        "max_dd_r": float(-dd.min()),
        "worst_day_r": float(daily.min()),
        "best_day_r": float(daily.max()),
        "worst_14d_r": float(cyc.min()),
        "median_14d_r": float(cyc.iloc[13:].median()),
        "max_losing_streak": int(mx),
        "risk_pips_mean": float(df.risk_pips.mean()),
    }


def history_gate(hist: dict, risk_levels) -> pd.DataFrame:
    rows = []
    for risk in risk_levels:
        rsize = risk * ACCT
        dd = hist["max_dd_r"] * rsize
        day = -hist["worst_day_r"] * rsize
        rows.append({
            "risk": risk,
            "max_dd_$": dd,
            "dd_multiple": dd / MAX_DD,
            "worst_day_$": day,
            "day_multiple": day / DAILY_DD,
            "passes": dd <= MAX_DD and day <= DAILY_DD,
        })
    return pd.DataFrame(rows)


def main():
    t0 = time.time()
    df = load_trades()
    hist = history(df)
    print(f"trades {len(df):,}  net_r sum {df.net_r.sum():+.2f}", flush=True)
    gate = history_gate(hist, (0.0025, 0.005, 0.0075, 0.01))
    print(gate.to_string(index=False), flush=True)
    blk = blocks(df)

    npaths = int(os.environ.get("MC_PATHS", "50000"))
    rows = []
    plans = [
        # risk, pad, pay_reset, shift, mode, block_weeks
        (0.0025, 0.0, 1, 0.0, "single", 1),
        (0.0050, 0.0, 1, 0.0, "single", 1),
        (0.0060, 0.0, 1, 0.0, "single", 1),
        (0.0075, 0.0, 1, 0.0, "single", 1),
        (0.0100, 0.0, 1, 0.0, "single", 1),
        (0.0050, 0.0, 1, 0.0, "career", 1),
        (0.0060, 0.0, 1, 0.0, "career", 1),
        (0.0075, 0.0, 1, 0.0, "career", 1),
        (0.0100, 0.0, 1, 0.0, "career", 1),
        # conservative: floor never resets after a payout
        (0.0050, 0.0, 0, 0.0, "single", 1),
        (0.0060, 0.0, 0, 0.0, "single", 1),
        (0.0075, 0.0, 0, 0.0, "single", 1),
        (0.0050, 0.0, 0, 0.0, "career", 1),
        (0.0060, 0.0, 0, 0.0, "career", 1),
        (0.0075, 0.0, 0, 0.0, "career", 1),
        # cost stress: +0.6 pips round trip on a ~10 pip stop
        (0.0050, 0.0, 0, -0.06, "single", 1),
        (0.0060, 0.0, 0, -0.06, "single", 1),
        # floating-loss pad: extra 0.5R charged against the floor
        (0.0050, 0.5, 0, 0.0, "single", 1),
        # serial-dependence check: 4-week blocks
        (0.0050, 0.0, 1, 0.0, "single", 4),
        (0.0075, 0.0, 1, 0.0, "single", 4),
        (0.0050, 0.0, 1, 0.0, "career", 4),
        (0.0075, 0.0, 1, 0.0, "career", 4),
    ]
    for risk, pad, pr, shift, mode, bw in plans:
        single = mode == "single"
        horizon = 900 if single else 730
        label = (f"{risk*100:g}% {'PR1' if pr else 'PR0'}"
                 f"{' shift' if shift else ''}{' pad' if pad else ''}"
                 f" bw{bw} {mode}")
        d = run_grid(blocks(df, bw), risk, npaths=npaths, horizon=horizon,
                     single=single, pad=pad, pay_reset=pr, shift_r=shift,
                     block_weeks=bw)
        row = summary(d, label, horizon, risk=risk, pad=pad,
                      pay_reset=pr, shift=shift, mode=mode, block_weeks=bw)
        rows.append(row)
        print(f"{label:36s} surv {row['survival']:.3f} "
              f"ch {row['challenge']:.3f} pay {row['payouts']:.2f} "
              f"net ${row['net_cash']:.0f} ({d.attrs['secs']:.0f}s)",
              flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT, "moneycheck.csv"), index=False)
    hist["gate"] = gate.to_dict("records")
    with open(os.path.join(OUT, "moneycheck_history.json"), "w",
              encoding="utf-8") as fh:
        json.dump(hist, fh, indent=2)
    print(out[["config", "p1", "p2_given_p1", "challenge", "survival",
               "payouts", "net_pay", "fees", "net_cash",
               "median_first_pay"]].to_string(index=False))
    print(f"total {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
