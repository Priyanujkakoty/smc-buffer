"""Fair value gaps. Wick-only geometry, exactly three candles.

Bullish: low[C3] > high[C1]  -> zone high[C1] .. low[C3]
Bearish: high[C3] < low[C1]  -> zone high[C3] .. low[C1]

The middle candle must close in the gap direction. This is the
smart-money-concepts convention: a bullish gap needs a bullish C2, a bearish
gap a bearish C2. `for_displacement` gets the same guarantee from the
displacement test, but `classic` is used to build the target book, so the
check is explicit there too.

For the baseline entry chain, C2 must be the displacement candle, so the gap
is confirmed on the bar after the structure shift.
"""
from __future__ import annotations


def classic(bars, i3: int, require_direction: bool = True):
    """Standard 3-candle gap ending at bar i3. Used by tests and auditing."""
    if i3 < 2:
        return None
    h1, l1 = float(bars.h[i3 - 2]), float(bars.l[i3 - 2])
    h3, l3 = float(bars.h[i3]), float(bars.l[i3])
    c2, o2 = float(bars.c[i3 - 1]), float(bars.o[i3 - 1])
    if l3 > h1:
        if require_direction and c2 <= o2:
            return None
        return dict(direction="long", c1=i3 - 2, c2=i3 - 1, c3=i3,
                    bottom=h1, top=l3, size=l3 - h1)
    if h3 < l1:
        if require_direction and c2 >= o2:
            return None
        return dict(direction="short", c1=i3 - 2, c2=i3 - 1, c3=i3,
                    bottom=h3, top=l1, size=l1 - h3)
    return None


def for_displacement(bars, i2: int, direction: str):
    """Gap whose middle candle is the displacement bar i2."""
    if i2 - 1 < 0 or i2 + 1 >= len(bars):
        return None
    h1, l1 = float(bars.h[i2 - 1]), float(bars.l[i2 - 1])
    h3, l3 = float(bars.h[i2 + 1]), float(bars.l[i2 + 1])
    if direction == "long":
        if l3 > h1:
            return dict(direction="long", c1=i2 - 1, c2=i2, c3=i2 + 1,
                        bottom=h1, top=l3, size=l3 - h1)
        return None
    if h3 < l1:
        return dict(direction="short", c1=i2 - 1, c2=i2, c3=i2 + 1,
                    bottom=h3, top=l1, size=l1 - h3)
    return None
