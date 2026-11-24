"""Confirmed fractal swings with an explicit confirmation lag.

A pivot at bar p is only usable at bar p + n (n bars to the right have
closed). Occurrence time and confirmation time are stored separately so the
engine can prove it never reads a swing before it existed.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

import numpy as np


@dataclass
class Swings:
    hi_occ: np.ndarray
    hi_lvl: np.ndarray
    hi_conf: np.ndarray
    lo_occ: np.ndarray
    lo_lvl: np.ndarray
    lo_conf: np.ndarray

    def __len__(self) -> int:
        return len(self.hi_occ) + len(self.lo_occ)


def find_swings(h: np.ndarray, l: np.ndarray, n: int = 3) -> Swings:
    """Strict fractal: high[p] > every high in p-n..p-1 and p+1..p+n."""
    h = np.asarray(h, dtype=float)
    l = np.asarray(l, dtype=float)
    size = len(h)
    hi = np.ones(size, dtype=bool)
    lo = np.ones(size, dtype=bool)
    for k in range(1, n + 1):
        a = np.zeros(size, dtype=bool)
        a[k:] = h[k:] > h[:-k]
        b = np.zeros(size, dtype=bool)
        b[:-k] = h[:-k] > h[k:]
        hi &= a & b
        a = np.zeros(size, dtype=bool)
        a[k:] = l[k:] < l[:-k]
        b = np.zeros(size, dtype=bool)
        b[:-k] = l[:-k] < l[k:]
        lo &= a & b
    hi[:n] = False
    hi[size - n:] = False
    lo[:n] = False
    lo[size - n:] = False
    hi_occ = np.flatnonzero(hi)
    lo_occ = np.flatnonzero(lo)
    return Swings(hi_occ=hi_occ, hi_lvl=h[hi_occ], hi_conf=hi_occ + n,
                  lo_occ=lo_occ, lo_lvl=l[lo_occ], lo_conf=lo_occ + n)


def latest_high(sw: Swings, at_idx: int, min_occ: int = 0,
                max_level: float | None = None):
    """Latest confirmed swing high usable at at_idx.

    Scans backwards from the newest confirmation, so the first hit is the most
    recent one. min_occ enforces 'inside the displacement leg'.
    """
    pos = int(bisect_right(sw.hi_conf, at_idx)) - 1
    while pos >= 0:
        occ = int(sw.hi_occ[pos])
        if occ < min_occ:
            return None
        lvl = float(sw.hi_lvl[pos])
        if max_level is None or lvl < max_level:
            return lvl, occ, int(sw.hi_conf[pos])
        pos -= 1
    return None


def latest_low(sw: Swings, at_idx: int, min_occ: int = 0,
               min_level: float | None = None):
    pos = int(bisect_right(sw.lo_conf, at_idx)) - 1
    while pos >= 0:
        occ = int(sw.lo_occ[pos])
        if occ < min_occ:
            return None
        lvl = float(sw.lo_lvl[pos])
        if min_level is None or lvl > min_level:
            return lvl, occ, int(sw.lo_conf[pos])
        pos -= 1
    return None
