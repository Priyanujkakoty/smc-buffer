"""Setup assembly: sweep -> displacement -> MSS -> FVG -> draw -> entry.

Every candidate carries a terminal reason. The engine never guesses: if a
stage fails, the setup is rejected with a code and the reason is logged.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field

from . import displacement, fvg, mss, pools as pool_mod, sweep
from .bias import bias_series, build_weekly, equilibrium, in_equilibrium
from .swings import find_swings
from .timecycle import cycle_index


@dataclass
class EngineResult:
    setups: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    counters: Counter = field(default_factory=Counter)
    weekly: object | None = None
    pools: list = field(default_factory=list)


def _setup_id(pair: str, direction: str, sweep_ts: int, level: float,
              created_ts: int) -> str:
    blob = f"{pair}|{direction}|{sweep_ts}|{level:.8f}|{created_ts}"
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def choose_dol(book, direction: str, entry: float, risk: float,
               kinds, min_rr: float):
    """Nearest live pool in the trade direction that clears min_rr.

    Returns (pool, rr, n_considered, n_below_min_rr).
    """
    if direction == "long":
        candidates = [p for p in book.live_above(entry) if p.kind in kinds]
    else:
        candidates = [p for p in reversed(book.live_below(entry))
                      if p.kind in kinds]
    below = 0
    for pool in candidates:
        rr = abs(pool.price - entry) / risk
        if rr >= min_rr:
            return pool, rr, len(candidates), below
        below += 1
    return None, None, len(candidates), below


def run_pair(pair: str, bars, cfg: dict) -> EngineResult:
    n = len(bars)
    res = EngineResult()
    C = res.counters
    C["bars"] = n

    swings = find_swings(bars.h, bars.l, int(cfg["structure"]["swing_fractal"]))
    weekly = build_weekly(bars, int(cfg["bias"]["min_weekly_bars"]))
    res.weekly = weekly
    ctx = bias_series(bars, weekly)
    bias = ctx["bias"]
    range_high = ctx["range_high"]
    range_low = ctx["range_low"]

    pools = pool_mod.build_pools(pair, bars, swings, weekly,
                                 cfg["time"].get("sessions_ny", []))
    res.pools = pools
    C["pools_registered"] = len(pools)
    book = pool_mod.PoolBook()
    ptr = 0

    cycle_anchor = int(cfg["time"]["cycle_anchor_minutes"])
    cycle_len = int(cfg["time"]["cycle_length_minutes"])
    cycles = cycle_index(bars.ny, cycle_anchor, cycle_len)

    disp_cfg = cfg["displacement"]
    sweep_cfg = cfg["sweep"]
    mss_lookback = int(sweep_cfg.get("mss_swing_lookback_bars", 12))
    max_to_mss = int(sweep_cfg["max_bars_to_mss"])
    fvg_cfg = cfg["fvg"]
    dol_cfg = cfg["dol"]
    risk_cfg = cfg["risk"]
    eq_cfg = cfg["equilibrium"]
    stop_buffer = float(risk_cfg["stop_buffer_atr"])
    min_rr = float(dol_cfg["min_rr"])
    dol_kinds = set(dol_cfg["kinds"])
    entry_fraction = float(fvg_cfg["entry_fraction"])
    large_gap_atr = float(fvg_cfg["large_gap_atr"])
    require_large = bool(fvg_cfg["require_large"])
    log_rejections = bool(cfg["logging"]["rejections"])
    max_events = int(cfg["logging"]["max_events"])

    def log(kind: str, bar: int, reason: str, **extra) -> None:
        if not log_rejections:
            return
        if len(res.events) >= max_events:
            C["events_dropped"] += 1
            return
        row = dict(pair=pair, kind=kind, bar=int(bar),
                   ts=int(bars.ts[bar]), reason=reason)
        row.update(extra)
        res.events.append(row)

    def sweep_fields(bar: int, verdict: dict) -> dict:
        return dict(level=verdict.get("level"), penetration=verdict["penetration"],
                    bar_high=float(bars.h[bar]), bar_low=float(bars.l[bar]),
                    close=float(bars.c[bar]), atr=float(bars.atr[bar]),
                    classification=verdict["classification"])

    active: list[dict] = []
    waiting: list[dict] = []

    for i in range(n):
        # 1. Pools become usable at their availability bar.
        while ptr < len(pools) and pools[ptr].conf_idx <= i:
            pool = pools[ptr]
            ptr += 1
            book.add(pool)

        # 2. Consume pools traded through by this bar. Several nearby levels
        #    cleared by one wick are one sweep event, not several.
        pool, taken = book.consume_highs_nearest(bars.h[i])
        if pool is not None:
            C["sweep_events_buy"] += 1
            C["pool_touched_buy"] += taken
            C["sweep_multi_level"] += max(0, taken - 1)
            verdict = sweep.classify(
                "buy", pool.price, bars.h[i], bars.l[i], bars.c[i],
                bars.atr[i], float(sweep_cfg["min_penetration_atr"]))
            if not verdict["valid"]:
                C["breakout_buy"] += 1
                fields = sweep_fields(i, verdict)
                fields["level"] = pool.price
                log("sweep", i, "breakout_above_level", pool_id=pool.pool_id,
                    cleared=taken, **fields)
            else:
                C["sweep_valid_short"] += 1
                if bias[i] != -1:
                    C["sweep_no_bias"] += 1
                else:
                    C["sweep_with_bias_short"] += 1
                    active.append(dict(direction="short", sweep_bar=i,
                                       level=pool.price, pool=pool,
                                       extreme=float(bars.h[i]),
                                       penetration=verdict["penetration"],
                                       sweep_high=float(bars.h[i]),
                                       sweep_low=float(bars.l[i]),
                                       sweep_close=float(bars.c[i]),
                                       expire=i + max_to_mss))

        pool, taken = book.consume_lows_nearest(bars.l[i])
        if pool is not None:
            C["sweep_events_sell"] += 1
            C["pool_touched_sell"] += taken
            C["sweep_multi_level"] += max(0, taken - 1)
            verdict = sweep.classify(
                "sell", pool.price, bars.h[i], bars.l[i], bars.c[i],
                bars.atr[i], float(sweep_cfg["min_penetration_atr"]))
            if not verdict["valid"]:
                C["breakout_sell"] += 1
                fields = sweep_fields(i, verdict)
                fields["level"] = pool.price
                log("sweep", i, "breakout_below_level", pool_id=pool.pool_id,
                    cleared=taken, **fields)
            else:
                C["sweep_valid_long"] += 1
                if bias[i] != 1:
                    C["sweep_no_bias"] += 1
                else:
                    C["sweep_with_bias_long"] += 1
                    active.append(dict(direction="long", sweep_bar=i,
                                       level=pool.price, pool=pool,
                                       extreme=float(bars.l[i]),
                                       penetration=verdict["penetration"],
                                       sweep_high=float(bars.h[i]),
                                       sweep_low=float(bars.l[i]),
                                       sweep_close=float(bars.c[i]),
                                       expire=i + max_to_mss))

        # 3. FVG confirmation for shifts found on the previous bar.
        pending = []
        for item in waiting:
            if item["check"] != i:
                pending.append(item)
                continue
            cand = item["cand"]
            gap = fvg.for_displacement(bars, item["c2"], cand["direction"])
            if gap is None:
                C["no_fvg"] += 1
                log("fvg", i, "no_gap_between_c1_and_c3",
                    sweep_ts=int(bars.ts[cand["sweep_bar"]]))
                continue
            C["fvg_ok"] += 1
            size_atr = gap["size"] / bars.atr[item["c2"]] \
                if bars.atr[item["c2"]] > 0 else 0.0
            is_large = size_atr >= large_gap_atr
            if require_large and not is_large:
                C["fvg_not_large"] += 1
                continue

            long_side = cand["direction"] == "long"
            if long_side:
                entry = gap["top"] - entry_fraction * gap["size"]
                stop = cand["extreme"] - stop_buffer * bars.atr[item["c2"]]
                risk = entry - stop
            else:
                entry = gap["bottom"] + entry_fraction * gap["size"]
                stop = cand["extreme"] + stop_buffer * bars.atr[item["c2"]]
                risk = stop - entry
            if risk <= 0:
                C["bad_risk"] += 1
                log("setup", i, "non_positive_risk")
                continue

            zone = equilibrium(float(range_high[i]), float(range_low[i]),
                               float(bars.atr[i]), float(eq_cfg["band_atr"]))
            if bool(eq_cfg["veto"]) and in_equilibrium(float(bars.c[i]), zone):
                C["equilibrium_veto"] += 1
                log("setup", i, "price_in_equilibrium", mid=zone["mid"],
                    band=zone["band"])
                continue

            pool, rr, considered, below = choose_dol(
                book, cand["direction"], entry, risk, dol_kinds, min_rr)
            if pool is None:
                reason = "no_dol" if considered == 0 else "rr_below_min"
                C[reason] += 1
                log("setup", i, reason, considered=considered,
                    below_min=below, entry=entry, risk=risk)
                continue
            C["dol_ok"] += 1

            setup = dict(
                setup_id=_setup_id(pair, cand["direction"],
                                   int(bars.ts[cand["sweep_bar"]]),
                                   cand["level"], int(bars.ts[i])),
                pair=pair, direction=cand["direction"],
                bias=int(bias[i]), week_id=int(ctx["week_id"][i]),
                sweep_bar=int(cand["sweep_bar"]),
                sweep_ts=int(bars.ts[cand["sweep_bar"]]),
                sweep_pool=cand["pool"].pool_id,
                sweep_kind=cand["pool"].kind,
                sweep_level=float(cand["level"]),
                sweep_extreme=float(cand["extreme"]),
                sweep_high=float(cand["sweep_high"]),
                sweep_low=float(cand["sweep_low"]),
                sweep_close=float(cand["sweep_close"]),
                sweep_penetration=float(cand["penetration"]),
                sweep_classification="sweep",
                mss_bar=int(item["c2"]),
                mss_ts=int(bars.ts[item["c2"]]),
                mss_level=float(item["mss"]["level"]),
                mss_swing_ts=int(bars.ts[item["mss"]["occ"]]),
                disp_body_atr=float(item["disp"]["body_atr"]),
                disp_body_ratio=float(item["disp"]["body_ratio"]),
                fvg_ts=int(bars.ts[i]),
                fvg_top=float(gap["top"]),
                fvg_bottom=float(gap["bottom"]),
                fvg_size_atr=float(size_atr),
                fvg_large=bool(is_large),
                dol_pool=pool.pool_id, dol_kind=pool.kind,
                dol_price=float(pool.price),
                dol_rr=float(rr),
                entry_limit=float(entry), stop=float(stop),
                risk=float(risk), rr=float(rr),
                cycle=int(cycles[i]),
                eq_mid=float(zone["mid"]), eq_band=float(zone["band"]),
                eq_range_high=float(zone["range_high"]),
                eq_range_low=float(zone["range_low"]),
                created_bar=i, created_ts=int(bars.ts[i]),
                expiry_bar=i + int(risk_cfg["entry_expiry_bars"]),
                status="pending")
            res.setups.append(setup)
            C["setups"] += 1
        waiting = pending

        # 4. A live sweep looks for displacement + MSS.
        survivors = []
        for cand in active:
            if i <= cand["sweep_bar"]:
                survivors.append(cand)
                continue
            if i > cand["expire"]:
                C["sweep_expired_no_mss"] += 1
                log("mss", i, "sweep_window_expired",
                    sweep_ts=int(bars.ts[cand["sweep_bar"]]),
                    level=cand["level"], penetration=cand["penetration"],
                    bar_high=cand["sweep_high"], bar_low=cand["sweep_low"],
                    close=cand["sweep_close"], classification="sweep")
                continue
            if cand["direction"] == "long":
                if bars.c[i] < cand["level"]:
                    C["sweep_failed_close_through"] += 1
                    log("sweep", i, "close_back_below_swept_low",
                        level=cand["level"], penetration=cand["penetration"],
                        bar_high=cand["sweep_high"], bar_low=cand["sweep_low"],
                        close=float(bars.c[i]), classification="invalidated")
                    continue
            else:
                if bars.c[i] > cand["level"]:
                    C["sweep_failed_close_through"] += 1
                    log("sweep", i, "close_back_above_swept_high",
                        level=cand["level"], penetration=cand["penetration"],
                        bar_high=cand["sweep_high"], bar_low=cand["sweep_low"],
                        close=float(bars.c[i]), classification="invalidated")
                    continue

            disp = displacement.test(
                float(bars.o[i]), float(bars.h[i]), float(bars.l[i]),
                float(bars.c[i]), float(bars.atr[i]), cand["direction"],
                float(disp_cfg["min_body_atr"]),
                float(disp_cfg["min_body_ratio"]))
            if not disp["ok"]:
                survivors.append(cand)
                continue
            C["displacement_ok"] += 1
            verdict = mss.qualify(swings, cand["direction"], i - 1,
                                  cand["sweep_bar"], float(bars.c[i]),
                                  mss_lookback)
            if not verdict["ok"]:
                C[f"mss_fail_{verdict['reason']}"] += 1
                log("mss", i, verdict["reason"],
                    close=float(bars.c[i]),
                    swing=verdict.get("level"))
                survivors.append(cand)
                continue
            C["mss_ok"] += 1
            waiting.append(dict(cand=cand, mss=verdict, c2=i,
                                check=i + 1, disp=disp))
        active = survivors

    C["active_unresolved"] = len(active)
    C["waiting_unresolved"] = len(waiting)
    return res
