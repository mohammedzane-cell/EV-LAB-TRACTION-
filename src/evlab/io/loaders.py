"""CSV loaders for the bench tests and the load points (tab 1).

File format (UTF-8, comma separator, decimal point):
- lines starting with "#" are comments; "# key: value" lines are kept as metadata
  (the demo files store their reference circuit as "# reference.<field>: value");
- one header line, each column written "name [unit]";
- files named *_demo.csv, or starting with a "# démo: …" line (data/tests/), are demo
  data (is_demo = True, labelled "démo").

Bench tests, columns essai, U [V], I [A], P [W], f [Hz], T [°C]; essai is
  dc            DC test: U = voltage between two terminals, I = DC current, T = winding temperature
  vide          no-load test: U = line voltage, I = line current, P = three-phase power
  rotor_bloque  locked-rotor test, same columns
Load points, columns g [-], U [V], I [A], T [N·m], cos_phi [-], f [Hz]; U is the line voltage;
  a load test is in motor operation, so 0 < g < 1. U, I, P, f of the tests must be > 0.

Unit conversions happen here only: line → phase voltage (U/√3), °C → K.
Errors are raised as LoaderError (a ValueError) with a French message.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from evlab.core import identification as ident
from evlab.core.session import MotorParams

T_ZERO_C = 273.15
BENCH_COLUMNS = {"essai": None, "U": "V", "I": "A", "P": "W", "f": "Hz", "T": "°C"}
LOAD_COLUMNS = {"g": "-", "U": "V", "I": "A", "T": "N·m", "cos_phi": "-", "f": "Hz"}
ESSAIS = ("dc", "vide", "rotor_bloque")
_HEADER = re.compile(r"^\s*([^\[\]]+?)\s*(?:\[\s*([^\]]*?)\s*\])?\s*$")


class LoaderError(ValueError):
    """A CSV file cannot be read; the message is in French, for the GUI."""


@dataclass(frozen=True)
class BenchTests:
    """Bench tests read from a CSV file (SI units, phase voltages)."""

    dc: ident.DcTest | None
    no_load: tuple[ident.NoLoadTest, ...]
    locked: ident.LockedRotorTest
    winding_temperature_k: float | None  # temperature during no-load / locked-rotor tests
    is_demo: bool
    path: str
    meta: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LoadPointsFile:
    """Load-test points read from a CSV file."""

    points: tuple[ident.LoadTestPoint, ...]
    is_demo: bool
    path: str
    meta: dict[str, str] = field(default_factory=dict)


def _read(path: str | Path, expected: dict[str, str | None],
          text: str | None = None) -> tuple[list[dict[str, str]], dict[str, str], str]:
    """Rows, metadata and name of a CSV file; `text` parses that content instead of reading `path`."""
    p = Path(path)
    name = p.name
    if text is None:
        try:
            text = p.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise LoaderError(f"Fichier introuvable : {p}") from None
        except UnicodeDecodeError:
            raise LoaderError(f"{name} : le fichier n'est pas en UTF-8") from None
    meta: dict[str, str] = {}
    lines: list[tuple[int, str]] = []
    for n, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            body = s[1:].strip()
            if ":" in body:
                k, v = body.split(":", 1)
                meta[k.strip()] = v.strip()
            continue
        lines.append((n, line))
    if not lines:
        raise LoaderError(f"{name} : fichier vide (aucune ligne d'en-tête ni de données)")

    header_line_no, header_text = lines[0]
    header = next(csv.reader(io.StringIO(header_text)))
    columns: dict[str, int] = {}
    for idx, raw in enumerate(header):
        m = _HEADER.match(raw)
        if not m:
            raise LoaderError(f"{name}, ligne {header_line_no} : en-tête illisible « {raw} »")
        col, unit = m.group(1), m.group(2)
        if col in expected:
            want = expected[col]
            if want is not None and unit != want:
                got = "aucune" if unit is None else f"« {unit} »"
                raise LoaderError(
                    f"{name} : unité incorrecte pour la colonne « {col} » : {got} (attendu : « {want} »)"
                )
            columns[col] = idx
    missing = [c for c in expected if c not in columns]
    if missing:
        noms = ", ".join(f"« {c} »" for c in missing)
        raise LoaderError(f"{name} : colonne(s) manquante(s) : {noms}")
    if len(lines) == 1:
        raise LoaderError(f"{name} : fichier vide (en-tête seul, aucune ligne de données)")

    rows = []
    for n, line in lines[1:]:
        cells = next(csv.reader(io.StringIO(line)))
        row = {c: (cells[i].strip() if i < len(cells) else "") for c, i in columns.items()}
        row["_line"] = str(n)
        rows.append(row)
    return rows, meta, name


def _num(row: dict[str, str], col: str, name: str, required: bool = True) -> float | None:
    s = row[col]
    if s == "":
        if required:
            raise LoaderError(f"{name}, ligne {row['_line']} : valeur manquante dans la colonne « {col} »")
        return None
    try:
        x = float(s)
    except ValueError:
        raise LoaderError(
            f"{name}, ligne {row['_line']} : « {s} » n'est pas un nombre (colonne « {col} », "
            "séparateur décimal : point)"
        ) from None
    if not math.isfinite(x):
        raise LoaderError(f"{name}, ligne {row['_line']} : valeur non finie dans la colonne « {col} »")
    return x


def _record(build, row: dict[str, str], name: str):
    try:
        return build()
    except LoaderError:
        raise
    except ValueError as exc:
        raise LoaderError(f"{name}, ligne {row['_line']} ({row.get('essai', 'point')}) : valeur invalide — {exc}") from None


def is_demo_file(path: str | Path, meta: dict[str, str] | None = None) -> bool:
    """Demo data: name *_demo.csv, or a "# démo: …" comment line (generated test datasets)."""
    return Path(path).name.endswith("_demo.csv") or "démo" in (meta or {})


POSITIVE = {"U": ("la tension U", "V"), "I": ("le courant I", "A"), "P": ("la puissance P", "W"),
            "f": ("la fréquence f", "Hz")}


def _positive(row: dict[str, str], col: str, name: str) -> float:
    """A reading that must be > 0, with a French message naming the quantity."""
    x = _num(row, col, name)
    if x <= 0:
        what, unit = POSITIVE[col]
        raise LoaderError(f"{name}, ligne {row['_line']} ({row.get('essai', 'point')}) : {what} doit être "
                          f"> 0 {unit} (valeur lue : « {row[col]} »)")
    return x


def load_bench_tests(path: str | Path, text: str | None = None) -> BenchTests:
    """Read DC, no-load and locked-rotor tests from a CSV file (see module docstring); `text`: content in memory."""
    rows, meta, name = _read(path, BENCH_COLUMNS, text)
    dc = None
    no_load: list[ident.NoLoadTest] = []
    locked: list[ident.LockedRotorTest] = []
    temps: list[float] = []
    for row in rows:
        essai = row["essai"].lower()
        if essai not in ESSAIS:
            raise LoaderError(
                f"{name}, ligne {row['_line']} : type d'essai « {row['essai']} » inconnu "
                f"(attendu : {', '.join(ESSAIS)})"
            )
        if essai == "dc":
            if dc is not None:
                raise LoaderError(f"{name} : plusieurs essais « dc » (un seul attendu)")
            u, i = _positive(row, "U", name), _positive(row, "I", name)
            t_c = _num(row, "T", name)
            dc = _record(lambda: ident.DcTest(v_dc=u, i_dc=i, temperature_k=t_c + T_ZERO_C), row, name)
            continue
        u, i, p, f = (_positive(row, c, name) for c in ("U", "I", "P", "f"))
        t_c = _num(row, "T", name, required=False)
        if t_c is not None:
            temps.append(t_c + T_ZERO_C)
        if essai == "vide":
            no_load.append(_record(lambda: ident.NoLoadTest.from_line(u, i, p, f), row, name))
        else:
            locked.append(_record(lambda: ident.LockedRotorTest.from_line(u, i, p, f), row, name))
    if not no_load:
        raise LoaderError(f"{name} : aucun essai « vide »")
    if len(locked) != 1:
        raise LoaderError(f"{name} : il faut exactement un essai « rotor_bloque » (trouvé : {len(locked)})")
    t_hot = sum(temps) / len(temps) if temps else None
    return BenchTests(dc, tuple(no_load), locked[0], t_hot, is_demo_file(path, meta), str(path), meta)


def load_load_points(path: str | Path, text: str | None = None) -> LoadPointsFile:
    """Read load-test points (g, U, I, T, cos φ, f) from a CSV file (see module docstring); `text`: content in memory."""
    rows, meta, name = _read(path, LOAD_COLUMNS, text)
    pts = []
    for row in rows:
        g, u, i, t, pf, f = (_num(row, c, name) for c in ("g", "U", "I", "T", "cos_phi", "f"))
        if u <= 0:
            raise LoaderError(f"{name}, ligne {row['_line']} : la tension U doit être > 0 V")
        if not 0.0 < g < 1.0:
            raise LoaderError(f"{name}, ligne {row['_line']} : glissement g = « {row['g']} » hors de ]0 ; 1[ "
                              "(un essai en charge est en fonctionnement moteur : 0 < g < 1)")
        pts.append(_record(lambda: ident.LoadTestPoint(
            slip=g, i_line=i, torque=t, power_factor=pf, v_phase=u / math.sqrt(3.0), f=f), row, name))
    if len(pts) < 3:
        raise LoaderError(f"{name} : au moins 3 points en charge sont nécessaires (trouvé : {len(pts)})")
    return LoadPointsFile(tuple(pts), is_demo_file(path, meta), str(path), meta)


@dataclass(frozen=True)
class Nameplate:
    """Nameplate values found in a file's "# plaque.*" lines (SI; None when absent)."""

    v_phase: float | None  # V
    f: float | None  # Hz
    pole_pairs: int | None
    rated_speed: float | None  # rad/s


PLATE_KEYS = {
    "v_phase": "plaque.tension_simple [V]",
    "f": "plaque.frequence [Hz]",
    "pole_pairs": "plaque.paires_de_poles",
    "rated_speed": "plaque.vitesse_nominale [tr/min]",
}


def nameplate(meta: dict[str, str]) -> Nameplate:
    """Nameplate from metadata; the rated speed is converted from tr/min to rad/s here."""
    vals: dict[str, float | int | None] = {}
    for field_name, key in PLATE_KEYS.items():
        raw = meta.get(key)
        if raw is None:
            vals[field_name] = None
            continue
        try:
            x = float(raw)
        except ValueError:
            raise LoaderError(f"plaque signalétique : « {raw} » n'est pas un nombre ({key})") from None
        if field_name == "pole_pairs":
            vals[field_name] = int(x)
        elif field_name == "rated_speed":
            vals[field_name] = x * 2.0 * math.pi / 60.0
        else:
            vals[field_name] = x
    return Nameplate(**vals)


def reference_motor(meta: dict[str, str]) -> MotorParams | None:
    """Reference circuit stored in a demo file's metadata ("# reference.<field>: value"), if any."""
    keys = ("v_phase", "f_rated", "pole_pairs", "r1", "r2p", "x_leak", "x_m", "r_fe")
    if not all(f"reference.{k}" in meta for k in keys):
        return None
    try:
        vals = {k: float(meta[f"reference.{k}"]) for k in keys}
        vals["pole_pairs"] = int(vals["pole_pairs"])
        if "reference.p_mech" in meta:
            vals["p_mech"] = float(meta["reference.p_mech"])
        return MotorParams(**vals, source=meta.get("reference.source", "référence"), is_demo=True)
    except ValueError as exc:
        raise LoaderError(f"métadonnées de référence invalides : {exc}") from None
