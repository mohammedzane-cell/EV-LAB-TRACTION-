"""Drive cycles from CSV (columns t [s], v [km/h]), validated and resampled to 1 s.

Official WLTC files are provided by the user as data/wltc_class1.csv and
data/wltc_class3.csv (never invented or downloaded here). Until then,
data/cycle_demo.csv is a synthetic urban cycle labelled "démo" (as are the
cycles of data/tests/, recognised by their "# démo: …" line).
Conversion km/h → m/s happens here only. Errors: LoaderError (French).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from evlab.core.vehicle import Cycle
from evlab.io.loaders import LoaderError, _num, _read, is_demo_file

CYCLE_COLUMNS = {"t": "s", "v": "km/h"}
KMH_TO_MS = 1.0 / 3.6
WLTC_FILES = {1: "wltc_class1.csv", 2: "wltc_class2.csv", 3: "wltc_class3.csv"}


def load_cycle(path: str | Path) -> Cycle:
    """Read a drive cycle, check that time strictly increases and v ≥ 0, resample to 1 s."""
    rows, meta, name = _read(path, CYCLE_COLUMNS)
    t = np.array([_num(r, "t", name) for r in rows])
    v = np.array([_num(r, "v", name) for r in rows])
    if t.size < 2:
        raise LoaderError(f"{name} : au moins 2 points sont nécessaires (trouvé : {t.size})")
    bad = np.nonzero(np.diff(t) <= 0)[0]
    if bad.size:
        k = int(bad[0])
        raise LoaderError(
            f"{name}, ligne {rows[k + 1]['_line']} : le temps doit être strictement croissant "
            f"({t[k]:g} s puis {t[k + 1]:g} s)"
        )
    neg = np.nonzero(v < 0)[0]
    if neg.size:
        raise LoaderError(f"{name}, ligne {rows[int(neg[0])]['_line']} : vitesse négative ({v[neg[0]]:g} km/h)")
    t1 = np.arange(t[0], t[0] + math.floor(t[-1] - t[0]) + 1.0)
    v1 = np.interp(t1, t, v) * KMH_TO_MS
    is_demo = is_demo_file(path, meta)
    label = Path(path).stem + (" (démo)" if is_demo else "")
    return Cycle(t=t1 - t1[0], v=v1, name=label, is_demo=is_demo)


def wltc_file(directory: str | Path, wltc_class: int) -> Path | None:
    """Path of the official WLTC file of a class in `directory`, or None if it is not there."""
    p = Path(directory) / WLTC_FILES.get(wltc_class, "")
    return p if p.is_file() else None
