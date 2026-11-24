"""Funnel, rejection table and trade statistics for the baseline run."""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .config import STRUCTURAL_INVARIANTS

NOTES = [
    ("MSS swing window",
     "The spec says 'last confirmed opposing swing within the displacement "
     "leg'. A 3-bar fractal formed after the sweep is usually not confirmed "
     "before the shift, so the implementation takes the latest confirmed "
     "swing whose occurrence is no earlier than 12 bars before the sweep "
     "(sweep.mss_swing_lookback_bars). A swing older than that is rejected "
     "as unrelated structure."),
    ("Weekly boundary",
     "Forex opens Sunday 17:00 NY, but the spec says bias freezes at Monday's "
     "open. Weeks are Monday 00:00 -> Monday 00:00 America/New_York."),
    ("Nearest draw vs minimum RR",
     "The engine walks pools outward from the entry and takes the first that "
     "clears 2R. The alternative reading rejects the setup when the nearest "
     "draw is below 2R. This changes trade count and is a config-adjacent "
     "decision, not an optimisation."),
    ("Draw ranking",
     "The concept notes rank pools time-first (previous session extreme), then "
     "price, then daily bias. The baseline ranks by price distance from the "
     "entry, because the entry price is fixed at setup time and the draw sets "
     "the RR. Time-first would pick a different target. Reported, not "
     "resolved."),
    ("Trade caps",
     "'Max 2 trades per day' and 'one position at a time' are enforced per "
     "pair, not portfolio-wide."),
    ("Entry windows",
     "The 13 blockers did not specify entry hours. Baseline allows fills "
     "02:00-05:00 and 07:00-11:00 NY only. Setups outside are created but "
     "never fill."),
    ("Reuse",
     "'An FVG can work again' from the concept notes is disabled by the "
     "one-setup-per-sweep rule. The baseline takes at most one trade per "
     "sweep."),
    ("Displacement dials",
     "1.0 ATR body and 0.60 body/range are baselines, not doctrine. They are "
     "the first candidates for the later ablation."),
    ("Session draw",
     "Session highs/lows are built for Asia 20:00-00:00, London 02:00-05:00 "
     "and NY AM 07:00-10:00 New York time, confirmed at session end. A run "
     "shorter than 8 bars (2 hours on 15m) is not a session reference."),
    ("One sweep event per bar",
     "A single wick can clear several nearby swing highs. They are one event, "
     "not several. The strict level is used: the lowest swept high for a "
     "short, the highest swept low for a long, so the close must be back "
     "inside every level the wick took out."),
    ("Stop placement",
     "The stop is 0.10 ATR beyond the sweep candle wick, per the spec. A "
     "deeper excursion before the MSS does not widen it; the sweep level "
     "close-through rule is the invalidation instead."),
    ("Time stop",
     "A 96-bar (24h) market-time stop is a risk control the source does not "
     "state. On EURUSD 2019-2026, 40 of 172 trades exited on it and produced "
     "20.5 of the 33.4 total R, so the headline depends on this dial. It is "
     "reported, not tuned."),
    ("Position sizing",
     "Risk is 0.25% of the INITIAL balance on every trade; the equity curve "
     "is marked but sizing does not compound."),
    ("Gross versus net",
     "The 1.4-pip round trip costs 0.087R at the median 18.8-pip stop. A "
     "zero-cost twin of the ten-pair 2019-2026 run earns +0.084R per trade; "
     "net is -0.003R. The edge is real but smaller than retail cost."),
    ("Fill and gap handling",
     "A limit order fills when the bar range touches it. If the bar opens "
     "beyond the limit, it fills at the open and the stop distance is "
     "recomputed from that fill. Stop and target exits use the bar open when "
     "the market gaps through the level. If stop and target both print in one "
     "bar, the stop is taken."),
    ("Session cutoff",
     "16:00 New York cancels unfilled orders. It does not force-close an open "
     "position; the 96-bar time stop does that."),
    ("News filter",
     "Implemented in news.py and shipped disabled. Enabling it requires a CSV "
     "of ts,currency,impact; fills inside the before/after window are blocked. "
     "No calendar file exists in the repository, so the baseline never "
     "exercised it."),
    ("Bug fixes after the first run",
     "The first pass had three defects: low pools were consumed on the wrong "
     "side of the bar, weekly buckets could shift by an hour across DST, and "
     "one wick could create duplicate sweep events. Fixing them changed the "
     "EURUSD result from +41.9R to +33.4R. No threshold was tuned."),
    ("Evidence conflict",
     "External tests (SSRN 2026, eXpeed 2026) find sweep-then-reverse does not "
     "work and that sweeps predict continuation. The baseline is reversal-only "
     "because the author specified it. The baseline run is the test of that "
     "claim, not a confirmation of it."),
]


def funnel(counters: dict) -> list[tuple[str, int]]:
    """Sequential stages. Percentages are pass rates between adjacent rows."""
    c = counters
    valid = c.get("sweep_valid_long", 0) + c.get("sweep_valid_short", 0)
    biased = (c.get("sweep_with_bias_long", 0)
              + c.get("sweep_with_bias_short", 0))
    return [
        ("bars", c.get("bars", 0)),
        ("liquidity pools registered", c.get("pools_registered", 0)),
        ("sweep events (levels traded through)", c.get("sweep_events_buy", 0)
         + c.get("sweep_events_sell", 0)),
        ("valid sweeps (wick through, close back inside)", valid),
        ("sweeps aligned with the frozen weekly bias", biased),
        ("MSS setups created (displacement + close + FVG + draw)",
         c.get("setups", 0)),
        ("entries filled", c.get("filled", 0)),
        ("trades closed", c.get("trades", 0)),
    ]


def terminal_breakdown(counters: dict) -> list[tuple[str, int]]:
    """Where every bias-aligned sweep ended. Should sum to the biased count."""
    c = counters
    draw_fail = (c.get("no_dol", 0) + c.get("rr_below_min", 0)
                 + c.get("equilibrium_veto", 0) + c.get("bad_risk", 0))
    return [
        ("setup created", c.get("setups", 0)),
        ("expired, no MSS in window", c.get("sweep_expired_no_mss", 0)),
        ("invalidated, close back through the swept level",
         c.get("sweep_failed_close_through", 0)),
        ("displacement found, no 3-candle FVG", c.get("no_fvg", 0)),
        ("MSS + FVG found, draw or RR rejected", draw_fail),
        ("still open at end of file", c.get("active_unresolved", 0)
         + c.get("waiting_unresolved", 0)),
    ]


def reject_table(events: list[dict]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame(columns=["kind", "reason", "count"])
    frame = pd.DataFrame(events)
    return (frame.groupby(["kind", "reason"]).size()
            .reset_index(name="count")
            .sort_values("count", ascending=False))


def trade_stats(trades: list[dict]) -> dict:
    if not trades:
        return dict(n=0)
    ordered = sorted(trades, key=lambda t: t["exit_ts"])
    net = np.array([t["net_r"] for t in ordered], dtype=float)
    wins = net > 0
    gross_win = net[wins].sum()
    gross_loss = -net[~wins].sum()
    cum = np.cumsum(net)
    peak = np.maximum.accumulate(cum)
    dd = float(np.min(cum - peak))
    net_pnl = float(sum(t["pnl"] for t in ordered))
    return dict(
        n=int(len(net)),
        wins=int(wins.sum()),
        losses=int((~wins).sum()),
        win_rate=round(float(wins.mean()) * 100, 2),
        avg_r=round(float(net.mean()), 4),
        median_r=round(float(np.median(net)), 4),
        sd_r=round(float(net.std(ddof=1)) if len(net) > 1 else 0.0, 4),
        total_r=round(float(net.sum()), 2),
        profit_factor=round(float(gross_win / gross_loss), 3)
        if gross_loss > 0 else None,
        max_drawdown_r=round(dd, 2),
        avg_bars=round(float(np.mean([t["bars_held"] for t in ordered])), 1),
        net_pnl=round(net_pnl, 2),
        avg_cost_r=round(float(np.mean([t["cost_r"] for t in ordered])), 4),
    )


def write_report(out_dir: str, cfg: dict, fingerprint: str,
                 counters: dict, events: list[dict], setups: list[dict],
                 trades: list[dict], fills: dict, per_pair: dict) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    table = funnel(counters)
    rejects = reject_table(events)
    stats = trade_stats(trades)

    pd.DataFrame(table, columns=["stage", "count"]).to_csv(
        os.path.join(out_dir, "funnel.csv"), index=False)
    rejects.to_csv(os.path.join(out_dir, "rejections.csv"), index=False)
    pd.DataFrame(setups).to_csv(os.path.join(out_dir, "setups.csv"), index=False)
    pd.DataFrame(trades).to_csv(os.path.join(out_dir, "trades.csv"), index=False)
    pd.DataFrame(events).to_csv(os.path.join(out_dir, "events.csv"), index=False)
    with open(os.path.join(out_dir, "counters.json"), "w",
              encoding="utf-8") as fh:
        json.dump(dict(counters), fh, indent=2, sort_keys=True)
        fh.write("\n")

    lines = ["# ICT Baseline - Deterministic Run", ""]
    lines.append(f"Config fingerprint: `{fingerprint}`")
    lines.append(f"Pairs: {', '.join(per_pair.keys())}")
    lines.append("")
    lines.append("## Structural invariants (not tunable)")
    lines.extend([f"- {item}" for item in STRUCTURAL_INVARIANTS])
    lines.append("")
    lines.append("## Filter funnel")
    lines.append("")
    lines.append("| Stage | Count | % of previous |")
    lines.append("|---|---:|---:|")
    prev = None
    for name, value in table:
        pct = "" if prev in (None, 0) else f"{100.0 * value / prev:.1f}%"
        lines.append(f"| {name} | {value} | {pct} |")
        prev = value if value else None
    lines.append("")
    lines.append("## Where every bias-aligned sweep ended")
    lines.append("")
    lines.append("| Outcome | Count |")
    lines.append("|---|---:|")
    for name, value in terminal_breakdown(counters):
        lines.append(f"| {name} | {value} |")
    lines.append("")
    lines.append("## Attempt counters")
    lines.append("")
    lines.append("| Counter | Count |")
    lines.append("|---|---:|")
    for key in ("breakout_buy", "breakout_sell", "sweep_multi_level",
                "displacement_ok", "mss_ok", "mss_fail_close_above_latest_swing",
                "mss_fail_close_below_latest_swing",
                "mss_fail_swing_too_distant", "fvg_ok", "dol_ok"):
        lines.append(f"| {key} | {counters.get(key, 0)} |")
    lines.append("")
    lines.append("## Rejections")
    lines.append("")
    if rejects.empty:
        lines.append("No rejection events recorded.")
    else:
        lines.append("| Stage | Reason | Count |")
        lines.append("|---|---|---:|")
        for _, row in rejects.iterrows():
            lines.append(f"| {row['kind']} | {row['reason']} | {row['count']} |")
    lines.append("")
    lines.append("## Executions cancelled after setup")
    lines.append("")
    lines.append("| Reason | Count |")
    lines.append("|---|---:|")
    for key in ("expired", "fvg_invalidated", "target_before_entry",
                "session_end", "daily_cap", "open_at_end"):
        lines.append(f"| {key} | {fills.get(key, 0)} |")
    lines.append("")
    lines.append("## Trades")
    lines.append("")
    if stats["n"] == 0:
        lines.append("No trades filled. The funnel above shows the binding stage.")
    else:
        lines.append("| Metric | Value |")
        lines.append("|---|---:|")
        for key in ("n", "wins", "losses", "win_rate", "avg_r", "median_r",
                    "sd_r", "total_r", "profit_factor", "max_drawdown_r",
                    "avg_bars", "avg_cost_r", "net_pnl"):
            lines.append(f"| {key} | {stats[key]} |")
    lines.append("")
    lines.append("## Contradictions and implementation choices")
    lines.append("")
    for title, body in NOTES:
        lines.append(f"- **{title}.** {body}")
    lines.append("")
    lines.append("## Per pair")
    lines.append("")
    lines.append("| Pair | Bars | Setups | Filled | Net R |")
    lines.append("|---|---:|---:|---:|---:|")
    for pair, row in per_pair.items():
        lines.append(f"| {pair} | {row['bars']} | {row['setups']} | "
                     f"{row['filled']} | {row['net_r']} |")
    lines.append("")

    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    summary = dict(fingerprint=fingerprint, counters=dict(counters),
                   stats=stats, fills=dict(fills), per_pair=per_pair)
    with open(os.path.join(out_dir, "summary.json"), "w",
              encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True, default=str)
        fh.write("\n")
    return summary
