"""Liquidity pools: confirmed swings, prior day and prior week extremes.

A pool is only usable from its confirmation bar. It is consumed by the first
bar that trades through it, which encodes 'a high or low is traded once
wicked'. Consumed pools can never be a draw on liquidity again.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass

import numpy as np

from .timecycle import day_key, runs, session_mask


@dataclass(frozen=True)
class Pool:
    pool_id: str
    kind: str        # swing_high swing_low pdh pdl pwh pwl
    side: str        # buy = stops above, sell = stops below
    price: float
    conf_idx: int    # first bar index where the pool is known
    occ_ts: int
    conf_ts: int


class PoolBook:
    """Two price-sorted books. Consumed ranges are contiguous by price."""

    def __init__(self) -> None:
        self.hi_prices: list[float] = []
        self.hi_pools: list[Pool] = []
        self.lo_prices: list[float] = []
        self.lo_pools: list[Pool] = []
        self.registered = 0
        self.consumed = 0

    def add(self, pool: Pool) -> bool:
        """Register a pool. Consumption is decided by the bar scan, never here.

        Dropping a pool because the bar that confirms it already traded through
        its price would hide a legitimate first-bar sweep of a prior-day or
        prior-week extreme.
        """
        self.registered += 1
        if pool.side == "buy":
            idx = bisect_right(self.hi_prices, pool.price)
            self.hi_prices.insert(idx, pool.price)
            self.hi_pools.insert(idx, pool)
        else:
            idx = bisect_right(self.lo_prices, pool.price)
            self.lo_prices.insert(idx, pool.price)
            self.lo_pools.insert(idx, pool)
        return True

    def consume_highs(self, bar_high: float) -> list[Pool]:
        """Pools strictly below the bar high are traded through."""
        idx = bisect_left(self.hi_prices, bar_high)
        if idx <= 0:
            return []
        batch = self.hi_pools[:idx]
        del self.hi_pools[:idx]
        del self.hi_prices[:idx]
        self.consumed += len(batch)
        return batch

    def consume_lows(self, bar_low: float) -> list[Pool]:
        """Pools strictly above the bar low are traded through."""
        idx = bisect_right(self.lo_prices, bar_low)
        if idx >= len(self.lo_pools):
            return []
        batch = self.lo_pools[idx:]
        del self.lo_pools[idx:]
        del self.lo_prices[idx:]
        self.consumed += len(batch)
        return batch

    def consume_highs_nearest(self, bar_high: float) -> tuple[Pool | None, int]:
        """Lowest pool strictly below the bar high, plus how many were taken.

        One bar can clear several nearby swing highs. They are one sweep event,
        not several. The lowest of the cleared highs is the strict one: the
        close must come back under every level the wick traded through.
        """
        idx = bisect_left(self.hi_prices, bar_high)
        if idx <= 0:
            return None, 0
        pool = self.hi_pools[0]
        batch = idx
        del self.hi_pools[:idx]
        del self.hi_prices[:idx]
        self.consumed += batch
        return pool, batch

    def consume_lows_nearest(self, bar_low: float) -> tuple[Pool | None, int]:
        """Highest pool strictly above the bar low, plus how many were taken.

        The close must come back above every low the wick traded through, so
        the highest of the cleared lows is the level that decides validity.
        """
        idx = bisect_right(self.lo_prices, bar_low)
        if idx >= len(self.lo_pools):
            return None, 0
        pool = self.lo_pools[-1]
        batch = len(self.lo_pools) - idx
        del self.lo_pools[idx:]
        del self.lo_prices[idx:]
        self.consumed += batch
        return pool, batch

    def live_above(self, price: float) -> list[Pool]:
        idx = bisect_right(self.hi_prices, price)
        return list(self.hi_pools[idx:])

    def live_below(self, price: float) -> list[Pool]:
        idx = bisect_left(self.lo_prices, price)
        return list(self.lo_pools[:idx])

    def live_count(self) -> int:
        return len(self.hi_pools) + len(self.lo_pools)


def build_pools(pair: str, bars, swings, weekly, sessions=()) -> list[Pool]:
    """All baseline pool types, sorted by confirmation bar."""
    pools: list[Pool] = []

    for occ, lvl, conf in zip(swings.hi_occ, swings.hi_lvl, swings.hi_conf):
        if conf >= len(bars):
            continue
        pools.append(Pool(f"{pair}:swing_high:{int(bars.ts[occ])}",
                          "swing_high", "buy", float(lvl), int(conf),
                          int(bars.ts[occ]), int(bars.ts[conf])))
    for occ, lvl, conf in zip(swings.lo_occ, swings.lo_lvl, swings.lo_conf):
        if conf >= len(bars):
            continue
        pools.append(Pool(f"{pair}:swing_low:{int(bars.ts[occ])}",
                          "swing_low", "sell", float(lvl), int(conf),
                          int(bars.ts[occ]), int(bars.ts[conf])))

    days = day_key(bars.ny)
    starts = np.flatnonzero(np.r_[True, days[1:] != days[:-1]])
    ends = np.r_[starts[1:], len(days)]
    for a, b in zip(starts, ends):
        if b >= len(bars):
            continue
        pools.append(Pool(f"{pair}:pdh:{int(days[a])}", "pdh", "buy",
                          float(np.max(bars.h[a:b])), int(b),
                          int(bars.ts[a]), int(bars.ts[b])))
        pools.append(Pool(f"{pair}:pdl:{int(days[a])}", "pdl", "sell",
                          float(np.min(bars.l[a:b])), int(b),
                          int(bars.ts[a]), int(bars.ts[b])))

    for j in range(len(weekly.end_ts)):
        if not weekly.complete[j]:
            continue
        conf = int(np.searchsorted(bars.ts, weekly.end_ts[j], side="left"))
        if conf >= len(bars):
            continue
        stamp = int(weekly.start_ts[j])
        pools.append(Pool(f"{pair}:pwh:{stamp}", "pwh", "buy",
                          float(weekly.high[j]), conf, stamp,
                          int(weekly.end_ts[j])))
        pools.append(Pool(f"{pair}:pwl:{stamp}", "pwl", "sell",
                          float(weekly.low[j]), conf, stamp,
                          int(weekly.end_ts[j])))

    for name, start, end in sessions:
        mask = session_mask(bars.ny, start, end)
        for a, b in runs(mask):
            if b - a < 8 or b >= len(bars):
                continue          # too short to be a session reference
            stamp = int(bars.ts[a])
            pools.append(Pool(f"{pair}:session_high:{name}:{stamp}",
                              "session_high", "buy",
                              float(np.max(bars.h[a:b])), int(b), stamp,
                              int(bars.ts[b])))
            pools.append(Pool(f"{pair}:session_low:{name}:{stamp}",
                              "session_low", "sell",
                              float(np.min(bars.l[a:b])), int(b), stamp,
                              int(bars.ts[b])))

    pools.sort(key=lambda p: (p.conf_idx, p.pool_id))
    return pools
