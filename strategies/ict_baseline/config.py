"""Configuration for the ICT deterministic baseline.

Two layers, deliberately kept apart:

STRUCTURAL_INVARIANTS
    The parts of the model that are not dials. They are enforced in code and
    are not read from the JSON. Changing one is a change to the model, not a
    parameter sweep.

DEFAULTS
    Every tunable threshold. Loaded from JSON, merged over these defaults.
    Unknown keys are rejected so a typo cannot silently fall back to a default.

The split matters: a parameter sweep may move DEFAULTS, never the invariants.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(HERE, "baseline_config.json")

# Not tunable. Listed here so the report can print them next to the results.
STRUCTURAL_INVARIANTS = (
    "FVG is the 3-candle wick-to-wick gap: low[C3] > high[C1] (bull) or "
    "high[C3] < low[C1] (bear). Body boundaries are never used.",
    "A sweep requires wick penetration and a close back inside the level. "
    "A close beyond the level is a breakout, not a sweep.",
    "An MSS requires a candle close beyond the swing. A wick through the "
    "swing is never an MSS.",
    "The MSS swing is the last confirmed opposing swing inside the "
    "displacement leg, not a distant structural swing.",
    "Weekly bias comes from the last fully closed weekly candle and is "
    "frozen until the next weekly close.",
    "Decision order is weekly structure -> direction -> draw -> setup -> "
    "entry. No draw, no trade.",
    "One setup per sweep event. No re-entry from the same sweep.",
    "Swing confirmation is lagged by the fractal length. No look-ahead.",
)

DEFAULTS = {
    "version": "1.0",
    "data": {
        "glob": "aqua/cache/*_5m_clean.parquet",
        "pairs": ["EURUSD", "GBPUSD"],
        "base_minutes": 5,
        "execution_minutes": 15,
        "start": None,
        "end": None,
    },
    "time": {
        "market_tz": "America/New_York",
        "cycle_anchor_minutes": 0,
        "cycle_length_minutes": 90,
        "entry_windows_ny": [["02:00", "05:00"], ["07:00", "11:00"]],
        "sessions_ny": [["asia", "20:00", "00:00"],
                        ["london", "02:00", "05:00"],
                        ["ny_am", "07:00", "10:00"]],
        "session_cutoff_ny": "16:00",
    },
    "structure": {
        "swing_fractal": 3,
        "atr_period": 14,
    },
    "bias": {
        "method": "close_vs_open",
        "min_weekly_bars": 400,
    },
    "equilibrium": {
        "range_source": "prior_week",
        "band_atr": 0.25,
        "veto": True,
    },
    "sweep": {
        "min_penetration_atr": 0.0,
        "max_bars_to_mss": 12,
        "mss_swing_lookback_bars": 12,
    },
    "displacement": {
        "min_body_atr": 1.0,
        "min_body_ratio": 0.60,
    },
    "fvg": {
        "large_gap_atr": 0.10,
        "require_large": False,
        "entry_fraction": 0.0,
    },
    "dol": {
        "min_rr": 2.0,
        "kinds": ["swing_high", "swing_low", "session_high", "session_low",
                  "pdh", "pdl", "pwh", "pwl"],
    },
    "risk": {
        "risk_pct": 0.25,
        "initial_balance": 10000.0,
        "stop_buffer_atr": 0.10,
        "max_trades_per_day": 2,
        "max_hold_bars": 96,
        "entry_expiry_bars": 10,
        "stop_loss_cap_r": None,
    },
    "costs": {
        "spread_pips": 1.0,
        "slippage_pips": 0.2,
        "commission_pips": 0.0,
    },
    "logging": {
        "rejections": True,
        "max_events": 200000,
    },
    "news": {
        "enabled": False,
        "csv": None,
        "before_minutes": 30,
        "after_minutes": 30,
        "impacts": ["high"],
    },
}


def _deep_merge(base: dict, override: dict, path: str = "") -> dict:
    out = copy.deepcopy(base)
    for key, val in override.items():
        where = f"{path}.{key}" if path else key
        if key not in out:
            raise KeyError(f"unknown config key: {where}")
        if isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val, where)
        else:
            out[key] = copy.deepcopy(val)
    return out


def load(path: str | None = None) -> dict:
    """Load JSON over defaults. Missing file returns defaults."""
    path = path or DEFAULT_CONFIG_PATH
    if not os.path.exists(path):
        return copy.deepcopy(DEFAULTS)
    with open(path, encoding="utf-8-sig") as fh:
        raw = json.load(fh)
    return _deep_merge(DEFAULTS, raw)


def save(cfg: dict, path: str | None = None) -> str:
    path = path or DEFAULT_CONFIG_PATH
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def fingerprint(cfg: dict) -> str:
    """Stable hash of the full config, for run reproducibility."""
    blob = json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def validate(cfg: dict) -> list[str]:
    """Cheap sanity checks. Returns warnings, raises on impossible values."""
    problems = []
    warnings = []
    execution = int(cfg["data"]["execution_minutes"])
    base = int(cfg["data"]["base_minutes"])
    if execution % base != 0:
        problems.append("execution_minutes must be a multiple of base_minutes")
    if int(cfg["structure"]["swing_fractal"]) < 1:
        problems.append("swing_fractal must be >= 1")
    if float(cfg["displacement"]["min_body_ratio"]) > 1.0:
        problems.append("min_body_ratio must be <= 1.0")
    if float(cfg["risk"]["risk_pct"]) <= 0:
        problems.append("risk_pct must be > 0")
    if int(cfg["risk"]["entry_expiry_bars"]) < 1:
        problems.append("entry_expiry_bars must be >= 1")
    if float(cfg["dol"]["min_rr"]) <= 0:
        problems.append("min_rr must be > 0")
    windows = cfg["time"]["entry_windows_ny"]
    for start, end in windows:
        if _hm(start) >= _hm(end):
            problems.append(f"entry window {start}-{end} is empty")
    for name, start, end in cfg["time"].get("sessions_ny", []):
        if _hm(start) == _hm(end):
            problems.append(f"session {name} is empty")
    if _hm(cfg["time"]["session_cutoff_ny"]) < _hm(windows[-1][1]):
        warnings.append("session_cutoff_ny is not after the last entry window")
    if cfg["bias"]["method"] != "close_vs_open":
        warnings.append(f"bias method {cfg['bias']['method']} is not implemented; "
                        "close_vs_open will be used")
    if cfg["equilibrium"]["range_source"] != "prior_week":
        warnings.append(
            f"range_source {cfg['equilibrium']['range_source']} is not "
            "implemented; the prior completed week is used")
    if cfg.get("news", {}).get("enabled") and not cfg["news"].get("csv"):
        problems.append("news.enabled is true but news.csv is not set")
    if problems:
        raise ValueError("; ".join(problems))
    return warnings


def _hm(text: str) -> int:
    hh, mm = str(text).split(":")
    return int(hh) * 60 + int(mm)
