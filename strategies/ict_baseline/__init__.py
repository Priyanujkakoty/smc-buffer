"""Deterministic ICT baseline: sweep -> displacement -> MSS -> FVG -> draw.

Modules are deliberately small and independently testable. The structural
rules live in code; every threshold lives in baseline_config.json.
"""
from .config import (DEFAULTS, STRUCTURAL_INVARIANTS, fingerprint, load,  # noqa: F401
                     save, validate)
