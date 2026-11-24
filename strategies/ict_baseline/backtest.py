"""Deterministic execution of pending limit orders.

Rules enforced here: one position at a time per pair, entry only inside the
configured NY windows, 10-bar limit expiry, cancel on invalidation or when the
target prints before the entry, maximum trades per NY day, time stop.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .data import pip_size
from .news import blackout_mask
from .timecycle import day_key, in_windows, minutes_of_day


@dataclass
class SimResult:
    trades: list[dict] = field(default_factory=list)
    fills: Counter = field(default_factory=Counter)
    equity: list[dict] = field(default_factory=list)


def simulate(pair: str, bars, setups: list[dict], cfg: dict) -> SimResult:
    res = SimResult()
    out = res.fills
    n = len(bars)
    pip = pip_size(pair)
    entry_mask = in_windows(bars.ny, cfg["time"]["entry_windows_ny"])
    news_mask = blackout_mask(pair, bars, cfg)
    cutoff_text = str(cfg["time"]["session_cutoff_ny"])
    cutoff = int(cutoff_text.split(":")[0]) * 60 + int(cutoff_text.split(":")[1])
    mins = minutes_of_day(bars.ny)
    day = day_key(bars.ny)
    max_hold = int(cfg["risk"]["max_hold_bars"])
    max_per_day = int(cfg["risk"]["max_trades_per_day"])
    stop_cap = cfg["risk"].get("stop_loss_cap_r")
    stop_cap = abs(float(stop_cap)) if stop_cap else None
    cost_pips = (float(cfg["costs"]["spread_pips"])
                 + 2.0 * float(cfg["costs"]["slippage_pips"])
                 + float(cfg["costs"]["commission_pips"]))
    risk_pct = float(cfg["risk"]["risk_pct"]) / 100.0
    initial = float(cfg["risk"]["initial_balance"])
    balance = initial

    setups = sorted(setups, key=lambda s: (s["created_bar"], s["setup_id"]))
    ptr = 0
    pending: list[dict] = []
    position: dict | None = None
    per_day: defaultdict = defaultdict(int)
    equity = balance
    res.equity.append(dict(ts=int(bars.ts[0]) if n else 0, balance=equity))

    def close_position(pos: dict, i: int, price: float, reason: str) -> None:
        nonlocal equity
        if reason == "stop":
            price = (min(float(bars.o[i]), pos["stop"])
                     if pos["direction"] == "long"
                     else max(float(bars.o[i]), pos["stop"]))
        elif reason == "target":
            price = (max(float(bars.o[i]), pos["target"])
                     if pos["direction"] == "long"
                     else min(float(bars.o[i]), pos["target"]))
        risk_pips = pos["risk"] / pip
        gross = ((price - pos["entry"]) if pos["direction"] == "long"
                 else (pos["entry"] - price)) / pos["risk"]
        cost_r = cost_pips / risk_pips if risk_pips > 0 else 0.0
        net = gross - cost_r
        # A broker stop caps the realised loss: fill at the stop plus a small
        # slippage allowance, including the spread already paid. Without this
        # a 1-pip stop on a 1.4-pip round trip books -2.4R, which no live
        # account can produce.
        capped = False
        if reason == "stop" and stop_cap is not None and net < -stop_cap:
            net = -stop_cap
            capped = True
        # Position size is fixed at risk_pct of the INITIAL balance.
        pnl = risk_pct * initial * net
        equity += pnl
        res.trades.append(dict(
            setup_id=pos["setup_id"], pair=pair,
            direction=pos["direction"], entry_ts=pos["entry_ts"],
            exit_ts=int(bars.ts[i]), entry=pos["entry"], stop=pos["stop"],
            target=pos["target"], exit_price=float(price),
            exit_reason=reason, bars_held=i - pos["entry_bar"],
            risk_pips=round(risk_pips, 4), gross_r=round(gross, 4),
            cost_r=round(cost_r, 4), net_r=round(net, 4), capped=capped,
            pnl=round(pnl, 2), balance=round(equity, 2),
            entry_day=int(day[pos["entry_bar"]]), cycle=pos["cycle"]))
        res.equity.append(dict(ts=int(bars.ts[i]), balance=equity))

    for i in range(n):
        # 1. Manage an open position. Stop wins ties inside one bar.
        if position is not None:
            pos = position
            long_side = pos["direction"] == "long"
            hit_stop = (bars.l[i] <= pos["stop"] if long_side
                        else bars.h[i] >= pos["stop"])
            hit_target = (bars.h[i] >= pos["target"] if long_side
                          else bars.l[i] <= pos["target"])
            if hit_stop:
                close_position(pos, i, pos["stop"], "stop")
                position = None
            elif hit_target:
                close_position(pos, i, pos["target"], "target")
                position = None
            elif i - pos["entry_bar"] >= max_hold:
                close_position(pos, i, float(bars.c[i]), "time")
                position = None

        # 2. New orders become live on the bar after creation.
        while ptr < len(setups) and setups[ptr]["created_bar"] < i:
            pending.append(setups[ptr])
            ptr += 1

        # 3. Cancel checks run before fills (conservative on same-bar conflicts).
        survivors = []
        for order in pending:
            long_side = order["direction"] == "long"
            if i > order["expiry_bar"]:
                out["expired"] += 1
                order["status"] = "expired"
                continue
            if mins[i] >= cutoff:
                out["session_end"] += 1
                order["status"] = "session_end"
                continue
            if long_side:
                if bars.c[i] < order["fvg_bottom"]:
                    out["fvg_invalidated"] += 1
                    order["status"] = "fvg_invalidated"
                    continue
                if bars.h[i] >= order["dol_price"]:
                    out["target_before_entry"] += 1
                    order["status"] = "target_before_entry"
                    continue
            else:
                if bars.c[i] > order["fvg_top"]:
                    out["fvg_invalidated"] += 1
                    order["status"] = "fvg_invalidated"
                    continue
                if bars.l[i] <= order["dol_price"]:
                    out["target_before_entry"] += 1
                    order["status"] = "target_before_entry"
                    continue
            survivors.append(order)
        pending = survivors

        # 4. At most one fill per bar, one position at a time.
        if position is None and pending and entry_mask[i] and not news_mask[i]:
            still_pending = []
            for order in pending:
                if position is not None:
                    still_pending.append(order)
                    continue
                long_side = order["direction"] == "long"
                fills = (bars.l[i] <= order["entry_limit"] if long_side
                         else bars.h[i] >= order["entry_limit"])
                if not fills:
                    still_pending.append(order)
                    continue
                if per_day[int(day[i])] >= max_per_day:
                    out["daily_cap"] += 1
                    order["status"] = "daily_cap"
                    continue

                base = (min(float(bars.o[i]), order["entry_limit"]) if long_side
                        else max(float(bars.o[i]), order["entry_limit"]))
                risk = abs(base - order["stop"])
                if risk <= 0:
                    out["bad_fill_risk"] += 1
                    order["status"] = "bad_fill_risk"
                    continue
                pos = dict(setup_id=order["setup_id"],
                           direction=order["direction"], entry=base,
                           stop=order["stop"], target=order["dol_price"],
                           entry_bar=i, entry_ts=int(bars.ts[i]),
                           cycle=order["cycle"], risk=risk)
                per_day[int(day[i])] += 1
                out["filled"] += 1
                order["status"] = "filled"
                position = pos

                hit_stop = (bars.l[i] <= pos["stop"] if long_side
                            else bars.h[i] >= pos["stop"])
                hit_target = (bars.h[i] >= pos["target"] if long_side
                              else bars.l[i] <= pos["target"])
                if hit_stop:
                    close_position(pos, i, pos["stop"], "stop")
                    position = None
                elif hit_target:
                    close_position(pos, i, pos["target"], "target")
                    position = None
                elif max_hold <= 0:
                    close_position(pos, i, float(bars.c[i]), "time")
                    position = None
            pending = still_pending

    for order in pending:
        order["status"] = "open_at_end"
        out["open_at_end"] += 1
    if position is not None:
        out["position_open_at_end"] += 1
    return res
