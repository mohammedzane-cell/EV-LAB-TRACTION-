"""The one motor shared by every module (ONE MOTOR, ONE CHAIN).

MotorParams holds the per-phase Γ equivalent circuit identified in tab 1.
Every downstream module (envelope, losses, vehicle, thermal, optimisation)
reads its motor from a Session, never from its own constants.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


def _check_positive(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite number > 0, got {value!r}")


def _check_non_negative(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite number >= 0, got {value!r}")


@dataclass(frozen=True)
class MotorParams:
    """Per-phase Γ equivalent circuit of the induction motor (star connection).

    Topology (TP3, Figure 1): V1 → r1 in series (carries I1) → node E;
    at E the magnetising branch r_fe ∥ j·x_m is in parallel with the rotor
    branch j·x_leak + r2p/g (carries I'2).

    Attributes:
        v_phase: rated phase voltage, V (RMS).
        f_rated: rated supply frequency, Hz.
        pole_pairs: number of pole pairs p (integer ≥ 1).
        r1: stator phase resistance, Ω (≥ 0).
        r2p: rotor resistance referred to the stator, R'2, Ω.
        x_leak: total leakage reactance N'2·ω at f_rated, Ω.
        x_m: magnetising reactance at f_rated, Ω.
        r_fe: iron-loss resistance, Ω.
        source: where the values come from ("TD5 Ex 1", "TP3", "fit", ...).
        is_demo: True if the values are demo/synthetic (must be labelled "démo").
    """

    v_phase: float
    f_rated: float
    pole_pairs: int
    r1: float
    r2p: float
    x_leak: float
    x_m: float
    r_fe: float
    source: str = "utilisateur"
    is_demo: bool = False

    def __post_init__(self) -> None:
        _check_positive("v_phase", self.v_phase)
        _check_positive("f_rated", self.f_rated)
        if isinstance(self.pole_pairs, bool) or not isinstance(self.pole_pairs, int) or self.pole_pairs < 1:
            raise ValueError(f"pole_pairs must be an integer >= 1, got {self.pole_pairs!r}")
        _check_non_negative("r1", self.r1)
        _check_positive("r2p", self.r2p)
        _check_positive("x_leak", self.x_leak)
        _check_positive("x_m", self.x_m)
        _check_positive("r_fe", self.r_fe)

    @property
    def omega_rated(self) -> float:
        """Rated electrical angular frequency ω = 2π·f, rad/s."""
        return 2.0 * math.pi * self.f_rated

    @property
    def omega_sync(self) -> float:
        """Rated synchronous mechanical speed Ω_s = ω / p, rad/s."""
        return self.omega_rated / self.pole_pairs

    @property
    def l_leak(self) -> float:
        """Total leakage inductance x_leak / ω, H."""
        return self.x_leak / self.omega_rated

    @property
    def l_m(self) -> float:
        """Magnetising inductance x_m / ω, H."""
        return self.x_m / self.omega_rated


def td5_ex1() -> MotorParams:
    """Reference motor of TD5 Exercise 1 (course data, not a demo)."""
    return MotorParams(
        v_phase=230.0,
        f_rated=50.0,
        pole_pairs=2,
        r1=0.0,
        r2p=2.0,
        x_leak=4.0,
        x_m=46.0,
        r_fe=230.0,
        source="TD5 Ex 1",
        is_demo=False,
    )


@dataclass
class Session:
    """Holds the single motor every tab works on. Defaults to TD5 Ex 1."""

    motor: MotorParams = field(default_factory=td5_ex1)

    def set_motor(self, motor: MotorParams) -> None:
        """Replace the shared motor (e.g. after identification in tab 1)."""
        if not isinstance(motor, MotorParams):
            raise ValueError(f"motor must be a MotorParams, got {type(motor).__name__}")
        self.motor = motor
