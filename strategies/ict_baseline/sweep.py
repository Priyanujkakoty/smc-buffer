"""Sweep classification.

A valid sweep needs wick penetration beyond a previously confirmed pool and a
close back on the original side. A close beyond the pool is a breakout and is
never traded as a reversal.
"""
from __future__ import annotations


def classify(side: str, level: float, bar_high: float, bar_low: float,
             bar_close: float, atr: float, min_penetration_atr: float = 0.0) -> dict:
    """side: 'buy' (pool above) or 'sell' (pool below)."""
    scale = float(atr) if (atr is not None and atr == atr and atr > 0) else 0.0
    min_pen = float(min_penetration_atr) * scale
    if side == "buy":
        penetration = bar_high - level
        swept = penetration > min_pen
        valid = swept and bar_close < level
    else:
        penetration = level - bar_low
        swept = penetration > min_pen
        valid = swept and bar_close > level
    return dict(swept=bool(swept), valid=bool(valid),
                penetration=float(penetration),
                classification="sweep" if valid else
                ("breakout" if swept else "untouched"))
