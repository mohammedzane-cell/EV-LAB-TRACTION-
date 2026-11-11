"""Numbers quoted by the course tab (tab 8): every « Exemple » and every « Avec votre moteur » value.

Pure functions (no Qt, no file I/O). Each value is computed by the core functions the
course page describes, so the course never quotes a number by hand:
- exemples(d): worked examples on the reference motor (noise-free) and on the démo
  files (noisy and noise-free), given as core objects by io.cours (which reads the files);
- valeurs_moteur(m): live values of the motor the chain uses (None: no motor yet).
Values are SI floats (or strings for labels); formatting is done by io.cours.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, replace

import numpy as np

from evlab.core import circuit, drive, losses, optimise, thermal, vehicle, winding
from evlab.core import identification as ident
from evlab.core.session import MotorParams, td5_ex1

T_ZERO_C = 273.15
RPM = 30.0 / math.pi  # rad/s → tr/min (display in the examples)
G_EX = 0.1  # slip of the circuit examples (rated point of the reference motor)
G_LOAD = 0.02  # first load point of the démo file
V_EX = 50.0 / 3.6  # m/s, road-force example
A_EX = 1.0  # m/s², road-force example
F_EX_HZ = 100.0  # Hz, frequency of the V/f and iron-loss examples
K_N_EX = 1.1  # rewinding factor of the tab 7 example
WINDING_EX = (36, 4, 3, 7)  # Z, 2p, m, y of tab 6
WINDING_FULL = (36, 4, 3, 9)
N_C_EX = 10  # turns per coil (tab 6 default)
FLUX_EX_WB = 0.01  # flux per pole of the tab 6 EMF example, Wb (tab 6 default)
CLASS_EX = "F"
COOL_S, COOL_FROM_S, COOL_EVERY_S = 7200, 1800.0, 600.0  # cooling-test example of tab 5 (s)
# air-gap example of tab 6 (FEM démo geometry A32): bore radius, slot opening, air gap (m), peak current (A)
BORE_R_M, SLOT_OPENING_M, GAP_M, I_PEAK_EX = 0.065, 0.0025, 0.0005, 6.0


@dataclass(frozen=True)
class DonneesDemo:
    """Inputs of the examples, as core objects (io.cours reads them from data/).

    records / points: the démo bench tests and load points (2,5 % noise);
    records_sans_bruit / points_sans_bruit: the same files generated without noise;
    reference: the circuit that generated them; noise: their relative noise (e.g. 0,025);
    cycle: the démo drive cycle.
    """

    records: ident.TestRecords
    points: tuple[ident.LoadTestPoint, ...]
    records_sans_bruit: ident.TestRecords
    points_sans_bruit: tuple[ident.LoadTestPoint, ...]
    reference: MotorParams
    noise: float
    cycle: vehicle.Cycle


def _quiet_compare(records: ident.TestRecords, points, reference: MotorParams) -> ident.MethodComparison:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ident.IdentifiabilityWarning)
        return ident.compare_methods(records, "both", points=points, layout="tp3", reference=reference,
                                     is_demo=True, source="Identification")


def _steps(rec: ident.TestRecords) -> dict[str, float]:
    """Intermediate values of the classical chain (same order as core.identification.run_identification)."""
    r1_cold = ident.r1_from_dc(rec.dc)
    r1 = ident.r1_at_temperature(r1_cold, rec.dc.temperature_k, rec.t_hot_k)
    v0 = np.array([t.v_phase for t in rec.no_load])
    p0p = np.array([t.p_total - 3.0 * r1 * t.i_line**2 for t in rec.no_load])
    p_mec = ident.mechanical_losses(v0, p0p)
    rated = min(rec.no_load, key=lambda t: abs(t.v_phase - rec.v_rated))
    rf_c, xm_c = ident.no_load_branch(rated, r1, p_mec, method="classical", layout="tp3")
    rf_e, xm_e = ident.no_load_branch(rated, r1, p_mec, method="exact", layout="tp3")
    r2_c, x_c = ident.locked_rotor(rec.locked, r1, rec.f_rated, method="classical", layout="tp3")
    r2_e, x_e = ident.locked_rotor(rec.locked, r1, rec.f_rated, r_fe=rf_e, x_m=xm_e, method="exact", layout="tp3")
    return dict(r1_cold=r1_cold, r1=r1, p_mec=p_mec, v0=rated.v_phase, i0=rated.i_line, p0=rated.p_total,
                q0=math.sqrt((3.0 * rated.v_phase * rated.i_line) ** 2 - rated.p_total**2),
                rf_c=rf_c, xm_c=xm_c, rf_e=rf_e, xm_e=xm_e, r2_c=r2_c, x_c=x_c, r2_e=r2_e, x_e=x_e)


def _exemples_identification(d: DonneesDemo) -> dict[str, float]:
    m = td5_ex1()
    s, s0 = _steps(d.records), _steps(d.records_sans_bruit)
    res = _quiet_compare(d.records, d.points, d.reference)
    fit, classical = res.motor("fit"), res.motor("classical")
    lo, hi = res.fit.ci95["r2p"]
    op_load = circuit.operating_point(classical, G_LOAD)
    # reference motor, noise-free locked-rotor test at 0,25·Vn (R1 = 0): the classical-formula bias
    v_cc = 0.25 * m.v_phase
    op_cc = circuit.operating_point(m, 1.0, v_phase=v_cc)
    cc = ident.LockedRotorTest(v_phase=v_cc, i_line=op_cc.i1, p_total=op_cc.p_in, f=m.f_rated)
    r2_ref_c, x_ref_c = ident.locked_rotor(cc, 0.0, m.f_rated, method="classical", layout="tp3")
    w_s = 2.0 * math.pi * m.f_rated / m.pole_pairs
    return {
        "dc_u": d.records.dc.v_dc, "dc_i": d.records.dc.i_dc, "dc_t": d.records.dc.temperature_k - T_ZERO_C,
        "r1_froid": s["r1_cold"], "r1_chaud": s["r1"], "t_chaud": d.records.t_hot_k - T_ZERO_C,
        "r1_hausse": 100.0 * (s["r1"] / s["r1_cold"] - 1.0),
        "ref_v": m.v_phase, "ref_u": math.sqrt(3.0) * m.v_phase,
        "p_mec": s["p_mec"], "p_mec_ref": d.reference.p_mech, "p_mec_sans_bruit": s0["p_mec"],
        "q0": s["q0"], "p0": s["p0"],
        "rf_classique": s["rf_c"], "xm_classique": s["xm_c"], "rf_exact": s["rf_e"], "xm_exact": s["xm_e"],
        "r2_classique": s["r2_c"], "x_classique": s["x_c"], "r2_exact": s["r2_e"], "x_exact": s["x_e"],
        "r2_exact_sans_bruit": s0["r2_e"], "x_exact_sans_bruit": s0["x_e"],
        "ref_zm_sur_z2": abs(circuit.magnetising_impedance(m)) / abs(complex(m.r2p, m.x_leak)),
        "ref_e_r2_classique": ident.relative_error(r2_ref_c, m.r2p),
        "ref_e_x_classique": ident.relative_error(x_ref_c, m.x_leak),
        "ref_i1": circuit.stator_current(m, G_EX), "ref_cos": circuit.power_factor(m, G_EX),
        "ref_i2": circuit.rotor_current(m, G_EX), "ref_couple": circuit.torque(m, G_EX),
        "ref_ws": w_s, "ref_ns": w_s * RPM,
        "ref_w": circuit.mechanical_speed(m, G_EX), "ref_n": circuit.mechanical_speed(m, G_EX) * RPM,
        "demo_n_g02": op_load.omega_mech * RPM, "demo_dt_g02": s["p_mec"] / op_load.omega_mech,
        "ref_gc": circuit.breakdown_slip(m), "ref_tmax": circuit.max_torque(m),
        "ref_pfer": circuit.operating_point(m, G_EX).p_fe, "ref_pfer_formule": 3.0 * m.v_phase**2 / m.r_fe,
        "r2_fit": fit.r2p, "r2_ci_bas": lo, "r2_ci_haut": hi,
        "e_r2_classique": ident.relative_error(classical.r2p, d.reference.r2p),
        "demo_ref_r2": d.reference.r2p, "demo_ref_x": d.reference.x_leak, "demo_ref_rf": d.reference.r_fe,
        "demo_ref_xm": d.reference.x_m, "bruit_pct": 100.0 * d.noise, "n_vide": float(len(d.records.no_load)),
    }


def demo_motor(d: DonneesDemo) -> MotorParams:
    """The motor the chain uses after the demo path of tab 1: load-point fit on the noisy démo files."""
    return _quiet_compare(d.records, d.points, d.reference).published


def _chain(m: MotorParams, cycle: vehicle.Cycle):
    """Envelope, map, sized vehicle, cycle and thermal run of tabs 2 to 5, with the démo settings."""
    dset = drive.demo_settings()
    st = losses.LossSettings(winding_temperature_k=m.r1_temperature_k)
    env = drive.envelope(m, dset)
    t_grid, w_grid = losses.default_grid(m, env, st)
    emap = losses.efficiency_map(m, t_grid, w_grid, dset, st, envelope=env)
    veh0 = vehicle.demo_quadricycle()
    sizing = vehicle.size_vehicle(m, env, st, veh0, cycle)
    veh = replace(veh0, gear_ratio=sizing.gear_ratio)
    res = vehicle.simulate(cycle, veh, m, env, emap, st)
    p = thermal.demo_thermal()
    pc, pf = thermal.cycle_losses(res, emap)
    th = thermal.simulate(p, pc, pf, n_cycles=10, copper_ref_k=thermal.map_copper_temperature(emap, m.r1_temperature_k),
                          insulation_class=CLASS_EX)
    return dset, st, env, emap, veh, sizing, res, p, pc, pf, th


def _exemples_chaine(d: DonneesDemo) -> dict[str, float]:
    ref = td5_ex1()
    m = demo_motor(d)
    dset, st, env, emap, veh, sizing, res, p, pc, pf, th = _chain(m, d.cycle)
    env_ref = drive.envelope(ref, dset)
    eta, t_best, w_best = losses.best_point(emap)
    ib = np.unravel_index(np.nanargmax(emap.eta), emap.eta.shape)  # same point as best_point
    at_best = {f"best_{k}": float(getattr(emap, k)[ib]) for k in ("p_cu1", "p_cu2", "p_fe", "p_mech", "p_inv", "p_out", "p_in", "f", "i1")}
    w0 = 2.0 * math.pi * m.f_rated / m.pole_pairs
    tau_f, tau_s = thermal.time_constants(p)
    mean_pc, mean_pf = float(np.mean(pc)), float(np.mean(pf))
    tw_ss, ts_ss = thermal.steady_state(p, mean_pc, mean_pf)
    t_class = thermal.INSULATION_CLASSES[CLASS_EX] + T_ZERO_C
    t_ex = t_class - 10.0
    # cooling test on the network: no losses from the steady state, resistance read every 10 min after 30 min
    cool = thermal.simulate(p, np.zeros(COOL_S), np.zeros(COOL_S), t0_k=(tw_ss, ts_ss))
    pick = (cool.t >= COOL_FROM_S) & (np.mod(cool.t, COOL_EVERY_S) == 0)
    r_read = np.array([circuit.copper_resistance(1.0, tk) for tk in cool.t_w[pick]])
    tau_fit, _t0 = thermal.fit_cooling_curve(cool.t[pick], r_read, 1.0, T_ZERO_C + 20.0, p.t_ambient_k)
    i_ex = len(env.omega) // 2
    f_traction = vehicle.road_force(veh, V_EX, A_EX)
    w_mot = vehicle.motor_speed(veh, V_EX)
    problem = optimise.Problem(m, dset, st, veh, d.cycle, p, CLASS_EX)
    base = optimise.evaluate(problem, problem.baseline())
    m_k = optimise.rewound(m, K_N_EX)
    return {
        # tab 2 — reference motor
        "ref_v_fn": float(drive.vf_voltage(ref, ref.f_rated, dset.boost)),
        "ref_v_f25": float(drive.vf_voltage(ref, 25.0, dset.boost)),
        "ref_v_f100": float(drive.vf_voltage(ref, F_EX_HZ, dset.boost)),
        "ref_x_f100": ref.x_leak * F_EX_HZ / ref.f_rated,
        "ref_tbd_fn": float(drive.breakdown_torque(ref, ref.f_rated, dset.boost)),
        "ref_tbd_f100": float(drive.breakdown_torque(ref, F_EX_HZ, dset.boost)),
        "ref_en": drive.rated_emf(ref),
        "ref_flux_f100": float(drive.flux_ratio(ref, drive.vf_voltage(ref, F_EX_HZ, dset.boost), F_EX_HZ)),
        "ref_base": env_ref.base_speed * RPM, "ref_fin_pc": env_ref.end_constant_power * RPM,
        "ref_pmax": env_ref.p_max, "ref_wmax": env_ref.omega_max * RPM,
        "ref_t_i_ex": float(env_ref.torque[i_ex]), "ref_w_i_ex": float(env_ref.omega[i_ex]) * RPM,
        "ref_f_i_ex": float(env_ref.f[i_ex]), "ref_g_i_ex": float(env_ref.slip[i_ex]),
        "ref_fr_i_ex": float(env_ref.slip[i_ex] * env_ref.f[i_ex]),
        "ref_flux_max": env_ref.max_flux_ratio, "i_max": dset.i_max, "marge": dset.margin, "f_max": dset.f_max,
        # tab 3 — démo motor
        "demo_r1_tw": losses.stator_resistance(m, st), "demo_tw": (st.winding_temperature_k or T_ZERO_C) - T_ZERO_C,
        "beta": st.beta, "part_frottements": st.friction_share, "demo_rf_f100": float(losses.iron_resistance(m, F_EX_HZ, st)), "demo_rf": m.r_fe,
        "demo_pmec_w0": float(losses.mechanical_loss(m, w0, st)), "demo_pmec_2w0": float(losses.mechanical_loss(m, 2 * w0, st)),
        "demo_n0": w0 * RPM, "demo_pmec": m.p_mech,
        "inv_p0": st.inverter_fixed_w, "inv_k": 100.0 * st.inverter_fraction,
        "demo_eta_max": 100.0 * eta, "demo_t_best": t_best, "demo_n_best": w_best * RPM,
        "demo_t_arbre_mid": float(losses.shaft_torque_limit(m, env, st)[i_ex]), "demo_t_em_mid": float(env.torque[i_ex]),
        "demo_n_mid": float(env.omega[i_ex]) * RPM,
        **at_best, "best_eta_bilan": 100.0 * at_best["best_p_out"] / at_best["best_p_in"],
        # tab 4 — démo motor, démo vehicle and cycle
        "veh_m": veh.mass, "veh_cxs": veh.cx_s, "veh_crr": veh.crr, "veh_r": veh.wheel_radius, "veh_eta": veh.gear_efficiency,
        "ex_v_kmh": V_EX * 3.6, "ex_a": A_EX, "ex_force": float(f_traction),
        "ex_couple": float(vehicle.motor_torque(veh, f_traction)), "ex_n_mot": float(w_mot) * RPM,
        "veh_g": sizing.gear_ratio, "veh_g_max": sizing.gear_ratio_max,
        "p_rated": sizing.rated_power, "pmr": sizing.pmr, "classe": float(sizing.wltc_class), "marge_cycle": sizing.min_margin,
        "cycle_km": res.summary.distance_m / 1000.0, "cycle_wh": res.summary.wh_per_km,
        "cycle_regen": res.summary.regen_percent, "cycle_wh_total": res.summary.energy_j / 3600.0,
        "t_0_50": vehicle.acceleration_time(veh, m, env, st, 50.0 / 3.6),
        # tab 5 — démo motor and network
        "th_cw": p.c_w, "th_cs": p.c_s, "th_rws": p.r_ws, "th_rsa": p.r_sa, "th_ta": p.t_ambient_k - T_ZERO_C,
        "tau_rapide_min": tau_f / 60.0, "tau_lent_min": tau_s / 60.0, "tau_essai_min": tau_fit / 60.0,
        "essai_n": float(np.count_nonzero(pick)), "essai_debut_min": COOL_FROM_S / 60.0,
        "p_cuivre_moy": mean_pc, "p_fer_moy": mean_pf, "tw_permanent": tw_ss - T_ZERO_C, "ts_permanent": ts_ss - T_ZERO_C,
        "tw_max": th.summary.t_max - T_ZERO_C, "tw_moy": th.summary.t_mean - T_ZERO_C, "marge_classe": th.summary.margin,
        "vie_h": th.summary.life_hours, "t_classe_ex": t_class - T_ZERO_C, "t_moins_10": t_ex - T_ZERO_C,
        "vie_classe": thermal.insulation_life(t_class, CLASS_EX), "vie_moins_10": thermal.insulation_life(t_ex, CLASS_EX),
        "vie_plus_10": thermal.insulation_life(t_class + 10.0, CLASS_EX),
        # tab 7 — démo motor, baseline design
        "k_n": K_N_EX, "k_n2": K_N_EX**2, "r2_kn": m_k.r2p, "x_kn": m_k.x_leak, "r2_k1": m.r2p, "x_k1": m.x_leak,
        "base_wh": base.wh_per_km, "base_t050": base.t_0_50, "base_tw": base.t_winding_max - T_ZERO_C,
        "base_i": base.i_cycle_max, "base_flux": base.flux_max, "base_marge": base.min_margin,
        "t_limite": problem.t_winding_limit - T_ZERO_C, "flux_limite": optimise.FLUX_LIMIT,
        "budget": float(optimise.BUDGET), "generations": float(optimise.generations(optimise.BUDGET, 15, 4)),
        "evals_point": float(optimise.run_evaluations(15, 4, optimise.generations(optimise.BUDGET, 15, 4))),
        "penalite": optimise.PENALTY,
    }


def _exemples_bobinage() -> dict[str, float]:
    w = winding.Winding(*WINDING_EX)
    w9 = winding.Winding(*WINDING_FULL)
    n = winding.turns_per_phase(w, N_C_EX)
    spec = winding.analytical_spectrum(w)
    rf = winding.rotating_field(w, 50.0, 1.0, turns_per_coil=N_C_EX)
    _, f_a = winding.phase_mmf(w, "A", turns_per_coil=N_C_EX)
    f1_6a = float(np.mean(winding.rotating_field(w, 50.0, I_PEAK_EX, turns_per_coil=N_C_EX).fundamental_amplitude))
    k_c = winding.carter_factor(2.0 * math.pi * BORE_R_M / w.z, SLOT_OPENING_M, GAP_M)
    return {
        "w_q": w.q, "w_tau": w.tau, "w_alpha": math.degrees(w.alpha), "w_y": w.y,
        "kd1": winding.distribution_factor(w, 1), "kp1_y7": winding.pitch_factor(w, 1),
        "kw1_y7": winding.winding_factor(w, 1), "kw5_y7": winding.winding_factor(w, 5), "kw7_y7": winding.winding_factor(w, 7),
        "kw1_y9": winding.winding_factor(w9, 1), "kw5_y9": winding.winding_factor(w9, 5), "kw7_y9": winding.winding_factor(w9, 7),
        "h5_y7": 100.0 * spec[5], "h7_y7": 100.0 * spec[7], "n_phase": n,
        "f_phase_max": float(np.max(f_a)), "f_tournant": float(np.mean(rf.fundamental_amplitude)),
        "f1_phase": winding.mmf_spectrum(w, f_a, normalise=False)[1],
        "rapport_tournant": float(np.mean(rf.fundamental_amplitude)) / winding.mmf_spectrum(w, f_a, normalise=False)[1],
        "w_flux": FLUX_EX_WB, "w_nc": float(N_C_EX), "emf": winding.emf(50.0, n, winding.winding_factor(w, 1), FLUX_EX_WB),
        "p_vitesse": float(winding.pole_pairs_from_speed(50.0, 2.0 * math.pi * 50.0 / 2.0)),
        "pas_dentaire_mm": 2.0 * math.pi * BORE_R_M / w.z * 1000.0, "ouverture_mm": SLOT_OPENING_M * 1000.0,
        "entrefer_mm": GAP_M * 1000.0, "i_crete": I_PEAK_EX, "f1_6a": f1_6a, "carter": k_c,
        "b_lisse": winding.gap_flux_density(f1_6a, GAP_M), "b_entrefer": winding.gap_flux_density(f1_6a, GAP_M, k_c),
    }


def _exemples_validation() -> dict[str, float]:
    m = td5_ex1()
    return {"ref_gc_closed": circuit.breakdown_slip(m), "ref_gc_num": circuit.breakdown(m)[0],
            "ref_tmax_num": circuit.breakdown(m)[1], "r20_75": circuit.copper_resistance(1.0, T_ZERO_C + 75.0),
            "wltc_22": float(vehicle.wltc_class(22.0)), "wltc_22p": float(vehicle.wltc_class(22.1)),
            "wltc_34": float(vehicle.wltc_class(34.0)), "wltc_34p": float(vehicle.wltc_class(34.1))}


def exemples(d: DonneesDemo) -> dict[str, float]:
    """Every « Exemple » number of the course pages, computed by the core (SI, or the unit named by the key)."""
    out: dict[str, float] = {}
    for part in (_exemples_identification(d), _exemples_chaine(d), _exemples_bobinage(), _exemples_validation()):
        dup = set(out) & set(part)
        if dup:
            raise ValueError(f"duplicate example keys: {sorted(dup)}")
        out.update(part)
    return out


def valeurs_moteur(m: MotorParams | None) -> dict[str, float | str] | None:
    """Live values of the motor the chain uses, for « Avec votre moteur »; None when there is no motor yet.

    Cheap quantities only (no envelope or map): they follow from the circuit and the démo
    drive and loss settings, so the page refreshes as soon as tab 1 publishes a motor.
    """
    if m is None:
        return None
    dset = drive.demo_settings()
    st = losses.LossSettings(winding_temperature_k=m.r1_temperature_k)
    w_s = 2.0 * math.pi * m.f_rated / m.pole_pairs
    e_n = drive.rated_emf(m)
    t_class = thermal.INSULATION_CLASSES[CLASS_EX] + T_ZERO_C
    out: dict[str, float | str] = {
        "source": m.source + (" (démo)" if m.is_demo else ""),
        "r1": m.r1, "r_fe": m.r_fe, "x_m": m.x_m, "x_leak": m.x_leak, "r2p": m.r2p, "p_mech": m.p_mech,
        "t_r1": (m.r1_temperature_k - T_ZERO_C) if m.r1_temperature_k is not None else "—",
        "g_c": circuit.breakdown_slip(m), "t_max": circuit.max_torque(m), "i_mu": circuit.magnetising_current(m),
        "v_n": m.v_phase, "f_n": m.f_rated, "p": float(m.pole_pairs), "n_s": w_s * RPM,
        "e_n": e_n, "tbd_fn": float(drive.breakdown_torque(m, m.f_rated, dset.boost)),
        "tbd_f100": float(drive.breakdown_torque(m, F_EX_HZ, dset.boost)),
        "rf_f100": float(losses.iron_resistance(m, F_EX_HZ, st)), "p_fer_n": 3.0 * e_n**2 / m.r_fe,
        "r1_tw": losses.stator_resistance(m, st),
        "r2_kn": optimise.rewound(m, K_N_EX).r2p, "x_kn": optimise.rewound(m, K_N_EX).x_leak,
        "flux_limite_v": optimise.FLUX_LIMIT * e_n / m.f_rated,
        "r1_nul": "oui : pas de pertes cuivre au stator" if thermal.stator_copper_missing(m) else "non",
    }
    env = drive.envelope(m, drive.demo_settings(n_points=150))
    veh = vehicle.demo_quadricycle()
    p_n = vehicle.rated_power(m, env, st)
    out.update(p_nom=p_n, pmr=p_n / veh.mass, classe=float(vehicle.wltc_class(p_n / veh.mass)),
               masse=veh.mass, base=env.base_speed * RPM, pmax=env.p_max)
    out["t_classe"] = t_class - T_ZERO_C
    out["r1_classe"] = (ident.r1_at_temperature(m.r1, m.r1_temperature_k, t_class)
                        if m.r1 > 0 and m.r1_temperature_k is not None else "—")
    return out
