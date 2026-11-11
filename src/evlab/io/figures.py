"""Report figures drawn with matplotlib from core results (never from screenshots).

Each function returns a matplotlib Figure (object API, no pyplot state), so the
report can render it at any size. Unit conversions for display only.
"""

from __future__ import annotations

import io
import math

import functools

import matplotlib
import numpy as np
from matplotlib.figure import Figure

from evlab.core import losses
from evlab.core import optimise as op
from evlab.core.drive import Envelope
from evlab.core.losses import EfficiencyMap
from evlab.core.session import MotorParams
from evlab.core.vehicle import Cycle, DriveResult
from evlab.palette import SERIES as S
from evlab.palette import mpl_rc
from evlab.io.format import fr_fixed

RPM = 60.0 / (2.0 * math.pi)
LIGHT_RC = mpl_rc("light")  # printed report: always the light theme of evlab.palette
KMH = 3.6
LEVELS = (50, 60, 70, 75, 78, 80, 82, 84, 86, 88, 90, 92, 94)


def _light(fn):
    """Draw a report figure with the light palette (rcParams of evlab.palette)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with matplotlib.rc_context(LIGHT_RC):
            return fn(*args, **kwargs)
    return wrapper


def _fig(width_cm: float, height_cm: float, ncols: int = 1) -> tuple[Figure, list]:
    fig = Figure(figsize=(width_cm / 2.54, height_cm / 2.54), layout="constrained")
    axes = [fig.add_subplot(1, ncols, k + 1) for k in range(ncols)]
    for ax in axes:
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.25)
    return fig, axes


@_light
def envelope_and_map(m: MotorParams, env: Envelope, emap: EfficiencyMap) -> Figure:
    """Left: torque and power envelope vs speed; right: efficiency contours with the shaft envelope."""
    fig, (a1, a2) = _fig(17.0, 6.2, 2)
    n = env.omega * RPM
    a1.plot(n, env.torque, color=S["blue"], lw=1.6, label="couple disponible")
    for a, b, c in ((0, env.base_speed, S["blue"]), (env.base_speed, env.end_constant_power, S["green"]),
                    (env.end_constant_power, env.omega_max, S["orange"])):
        if b > a:
            a1.axvspan(a * RPM, b * RPM, color=c, alpha=0.10)
    a1.set_xlabel("Vitesse (tr/min)", fontsize=8)
    a1.set_ylabel("Couple (N·m)", fontsize=8)
    ap = a1.twinx()
    ap.plot(n, env.power / 1000, color=S["red"], lw=1.2, ls="--", label="puissance")
    ap.set_ylabel("Puissance (kW)", fontsize=8)
    ap.tick_params(labelsize=7)
    a1.set_title("Enveloppe V/f + défluxage", fontsize=9)
    lines = a1.get_lines() + ap.get_lines()
    a1.legend(lines, [ln.get_label() for ln in lines], fontsize=7, loc="upper right")
    eta = 100 * emap.eta
    a2.contourf(emap.speed * RPM, emap.torque, eta, levels=np.arange(0, 101, 2.5), cmap="viridis")
    levels = [lv for lv in LEVELS if np.nanmin(eta) < lv < np.nanmax(eta)]
    if levels:
        cs = a2.contour(emap.speed * RPM, emap.torque, eta, levels=levels, colors="white", linewidths=0.6)
        a2.clabel(cs, fmt=lambda v: f"{fr_fixed(v, 0)} %", fontsize=6)
    a2.plot(n, losses.shaft_torque_limit(m, env, emap.settings), color=S["red"], lw=1.4)
    a2.set_xlabel("Vitesse (tr/min)", fontsize=8)
    a2.set_ylabel("Couple à l'arbre (N·m)", fontsize=8)
    a2.set_title("Rendement onduleur + moteur", fontsize=9)
    return fig


@_light
def cycle_figure(cycle: Cycle, res: DriveResult) -> Figure:
    """Vehicle speed (km/h) and battery power (kW) over the cycle; points outside the envelope in red."""
    fig, (a1,) = _fig(17.0, 5.6)
    a1.plot(cycle.t, cycle.v * KMH, color=S["blue"], lw=1.2, label="vitesse")
    if res.outside.any():
        a1.plot(res.t[res.outside], res.v[res.outside] * KMH, "o", color=S["red"], ms=3, label="hors enveloppe")
    a1.set_xlabel("Temps (s)", fontsize=8)
    a1.set_ylabel("Vitesse (km/h)", fontsize=8)
    a2 = a1.twinx()
    a2.plot(res.t, res.p_battery / 1000, color=S["green"], lw=0.8, label="puissance batterie")
    a2.axhline(0, color=S["grey"], lw=0.6)
    a2.set_ylabel("Puissance batterie (kW)", fontsize=8)
    a2.tick_params(labelsize=7)
    lines = a1.get_lines() + a2.get_lines()[:1]
    a1.legend(lines, [ln.get_label() for ln in lines], fontsize=7, loc="upper left")
    a1.set_title(f"Cycle {cycle.name}", fontsize=9)
    return fig


@_light
def pareto_figure(pr: op.ParetoResult) -> Figure:
    """Admissible evaluations, Pareto front and baseline in the (0–50 km/h, Wh/km) plane."""
    fig, (ax,) = _fig(11.0, 6.0)
    feas = [e for e in pr.log if e.feasible and math.isfinite(e.t_0_50)]
    if feas:
        ax.scatter([e.t_0_50 for e in feas], [e.wh_per_km for e in feas], s=4, color=S["grey"], alpha=0.4,
                   label="évaluations admissibles")
    if pr.front:
        ax.plot([e.t_0_50 for e in pr.front], [e.wh_per_km for e in pr.front], "o--", color=S["green"], ms=4,
                lw=0.8, label="front de Pareto")
    b = pr.baseline
    if math.isfinite(b.t_0_50):
        ax.plot([b.t_0_50], [b.wh_per_km], "*", color=S["orange"], ms=11, label="base")
    ax.set_xlabel("0–50 km/h (s)", fontsize=8)
    ax.set_ylabel("Consommation (Wh/km)", fontsize=8)
    ax.legend(fontsize=7)
    return fig


def png_bytes(fig: Figure, dpi: int = 200) -> bytes:
    """Render a figure to PNG in memory."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi)
    return buf.getvalue()
