"""Displacement test.

One candle, in the trade direction, with a body large relative to ATR and to
its own range, and (optionally) a close beyond the prior candle's opposite
extreme. No numerical threshold here is doctrine; the defaults are dials.

`prior_extreme` is the prior candle's high for a long and low for a short. When
provided, the candle must close beyond it. That is the codeable proxy in
CONCEPT_DEFINITIONS.md section 9.1: "closes beyond the prior candle's opposite
extreme, body >= 60% of range, and forms an FVG".
"""
from __future__ import annotations


def test(o: float, h: float, l: float, c: float, atr: float, direction: str,
         min_body_atr: float, min_body_ratio: float,
         prior_extreme: float | None = None) -> dict:
    body = (c - o) if direction == "long" else (o - c)
    rng = h - l
    ratio = (body / rng) if rng > 0 else 0.0
    body_atr = (body / atr) if atr and atr > 0 else 0.0
    if prior_extreme is None:
        beyond = True
    elif direction == "long":
        beyond = c > float(prior_extreme)
    else:
        beyond = c < float(prior_extreme)
    ok = (body > 0 and body_atr >= min_body_atr and ratio >= min_body_ratio
          and beyond)
    if ok:
        reason = ""
    elif body <= 0:
        reason = "wrong_direction"
    elif body_atr < min_body_atr or ratio < min_body_ratio:
        reason = "body_too_small"
    else:
        reason = "close_not_beyond_prior"
    return dict(ok=bool(ok), body=float(body), body_atr=float(body_atr),
                body_ratio=float(ratio), beyond_prior=bool(beyond),
                reason=reason)
