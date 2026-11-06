"""French display formatting (decimal comma), shared by the GUI and the reports. Formatting only: no physics."""

from __future__ import annotations

import math


def fr(x: float | None, sig: int = 3) -> str:
    """Number with `sig` significant digits and a decimal comma: 4.18 → "4,18", 230 → "230"."""
    if x is None or not math.isfinite(x):
        return "—"
    if x == 0:
        return "0"
    decimals = max(0, sig - 1 - int(math.floor(math.log10(abs(x)))))
    return f"{x:.{decimals}f}".replace(".", ",")


def fr_fixed(x: float | None, decimals: int) -> str:
    """Number with a fixed number of decimals and a decimal comma."""
    if x is None or not math.isfinite(x):
        return "—"
    return f"{x:.{decimals}f}".replace(".", ",")


def fr_pct(e: float | None) -> str:
    """Signed percentage with one decimal: 3.5 → "+3,5 %"."""
    if e is None or not math.isfinite(e):
        return ""
    return f"{e:+.1f} %".replace(".", ",")
