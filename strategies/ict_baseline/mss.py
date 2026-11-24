"""Market structure shift.

The shift is a CLOSE beyond the latest confirmed opposing swing. If the latest
confirmed opposing swing is too old, it is not part of this leg and the setup
is rejected rather than reaching for a distant structural level.
"""
from __future__ import annotations

from .swings import Swings, latest_high, latest_low


def qualify(swings: Swings, direction: str, at_idx: int, sweep_bar: int,
            close: float, lookback_bars: int = 12) -> dict:
    """at_idx: last bar whose close is already known (the bar before entry).

    lookback_bars bounds how far before the sweep the broken swing may have
    formed. Beyond that the swing is treated as unrelated structure. Zero
    disables the age bound: the last confirmed swing at the sweep is used
    however old it is.
    """
    min_occ = (max(0, int(sweep_bar) - int(lookback_bars))
               if int(lookback_bars) > 0 else 0)
    if direction == "long":
        found = latest_high(swings, at_idx, min_occ=0)
        if found is None:
            return dict(ok=False, reason="no_opposing_swing")
        level, occ, conf = found
        if occ < min_occ:
            return dict(ok=False, reason="swing_too_distant", level=level,
                        occ=occ, conf=conf)
        if close > level:
            return dict(ok=True, level=level, occ=occ, conf=conf)
        return dict(ok=False, reason="close_below_latest_swing", level=level,
                    occ=occ, conf=conf)

    found = latest_low(swings, at_idx, min_occ=0)
    if found is None:
        return dict(ok=False, reason="no_opposing_swing")
    level, occ, conf = found
    if occ < min_occ:
        return dict(ok=False, reason="swing_too_distant", level=level,
                    occ=occ, conf=conf)
    if close < level:
        return dict(ok=True, level=level, occ=occ, conf=conf)
    return dict(ok=False, reason="close_above_latest_swing", level=level,
                occ=occ, conf=conf)
