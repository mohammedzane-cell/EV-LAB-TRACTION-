"""core/scene3d.py: closed, outward meshes with exact volumes; motor geometry consistent with the winding
(slot table, counts, cutaway); powertrain kinematics; playback of a real simulated cycle checked against
independent quantities (distance / wheel radius, the vehicle's own energy balance, battery and thermal series)."""

import math
from dataclasses import replace

import numpy as np
import pytest

from evlab.core import battery as bt
from evlab.core import scene3d as sc
from evlab.core import vehicle as vh
from evlab.core import winding as wd

W = wd.Winding(36, 4, 3, 7)
G = sc.illustrative_geometry(W)


def _closed_and_outward(m: sc.Mesh) -> None:
    """Every directed edge appears once and its reverse once (closed, consistently oriented, after welding
    coincident vertices), and every non-degenerate face points along its vertex normals."""
    key = np.round(m.positions / 1e-7).astype(np.int64)
    _, weld = np.unique(key, axis=0, return_inverse=True)
    tri = weld.ravel()[m.indices]
    p = m.positions[m.indices]
    face = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    area = np.linalg.norm(face, axis=1)
    good = area > 1e-14
    assert np.all(np.einsum("ij,ij->i", face[good], m.normals[m.indices].mean(axis=1)[good]) > 0)
    edges = np.concatenate([tri[good][:, [0, 1]], tri[good][:, [1, 2]], tri[good][:, [2, 0]]])
    directed = {tuple(e) for e in edges}
    assert len(directed) == len(edges)  # no directed edge twice
    assert all((b, a) in directed for a, b in directed)  # each edge has its opposite: closed


@pytest.mark.parametrize("r_in, r_out, span, n", [(0.05, 0.08, 2 * math.pi, 96), (0.05, 0.08, 1.0, 7),
                                                  (0.0, 0.02, 2 * math.pi, 24), (0.0, 0.03, 2.5, 9)])
def test_annular_sector_is_closed_with_its_exact_volume(r_in, r_out, span, n):
    m = sc.annular_sector(r_in, r_out, -0.1, 0.05, 0.3, span, n)
    assert m.volume() == pytest.approx(sc.sector_volume(r_in, r_out, 0.15, span, n), rel=1e-9)
    _closed_and_outward(m)
    assert np.allclose(np.linalg.norm(m.normals, axis=1), 1.0)


def test_box_sphere_cylinder():
    b = sc.box((0.1, -0.2, 0.3), (0.2, 0.1, 0.4))
    assert b.volume() == pytest.approx(0.2 * 0.1 * 0.4)
    _closed_and_outward(b)
    s = sc.sphere((0, 0, 0), 0.01, 12, 24)
    assert 0.95 * 4 / 3 * math.pi * 1e-6 < s.volume() < 4 / 3 * math.pi * 1e-6
    _closed_and_outward(s)
    c = sc.cylinder_between((0.1, 0.2, 0.3), (0.4, -0.2, 0.3), 0.01, 16)
    assert c.volume() == pytest.approx(sc.sector_volume(0.0, 0.01, 0.5, 2 * math.pi, 16))
    lo, hi = c.bounds()
    assert lo[0] == pytest.approx(0.1, abs=0.011) and hi[0] == pytest.approx(0.4, abs=0.011)
    r = sc.rotation_from_z((1.0, 2.0, -2.0))
    assert np.allclose(r @ [0, 0, 1], np.array([1, 2, -2]) / 3) and np.allclose(r.T @ r, np.eye(3))


def test_rotor_bar_count_avoids_forbidden_combinations():
    assert sc.rotor_bar_count(36, 2) == 28
    for z in (24, 36, 48, 54, 72):
        for p in (1, 2, 3, 4):
            n = sc.rotor_bar_count(z, p)
            assert n % 2 == 0 and abs(z - n) not in {0, 1, 2, p, 2 * p, 2 * p - 1, 2 * p + 1, 2 * p - 2, 2 * p + 2}
    with pytest.raises(ValueError):
        sc.rotor_bar_count(36, 0)


def _angles(m: sc.Mesh) -> np.ndarray:
    return np.arctan2(m.positions[:, 1], m.positions[:, 0])


def test_motor_matches_the_winding():
    parts = {p.key: p for p in sc.motor_parts(G, W)}
    table = wd.slot_table(W)
    for ph in "ABC":
        part = parts[f"winding_{ph}"]
        assert part.facts["coil_sides"] == 2 * 36 // 3 and part.facts["coils"] == 12
        assert part.facts["kw1"] == pytest.approx(0.9019, abs=1e-4)
        # coil sides of each layer (only they have vertices on the radius between the layers): their slots
        # are exactly those holding phase ph in that layer of the slot table
        r = np.hypot(part.mesh.positions[:, 0], part.mesh.positions[:, 1])
        for layer, edge in (("top", 1), ("bottom", 0)):
            on = np.isclose(r, sc.layer_radii(G)[layer][edge], atol=1e-9)
            slots = set(np.round(_angles(part.mesh)[on] / G.slot_pitch).astype(int) % 36)
            assert slots == {s for s, sl in enumerate(table) if getattr(sl, layer)[0] == ph}, (ph, layer)
    for p in parts.values():
        _closed_and_outward(p.mesh) if p.mesh.n_triangles < 3000 else None
        assert p.mesh.volume() > 0
    # the rotor parts turn, the rest is stationary
    assert {k for k, p in parts.items() if p.spin == "motor"} == {"rotor_core", "rotor_bars", "end_rings", "shaft"}
    lo, hi = parts["stator_core"].mesh.bounds()
    assert hi[0] == pytest.approx(G.r_out, rel=1e-3) and hi[2] == pytest.approx(G.stack / 2)
    bars = parts["rotor_bars"].mesh
    assert len(set(np.round(_angles(bars) / (2 * math.pi / 28)).astype(int) % 28)) == 28
    with pytest.raises(ValueError):
        sc.motor_parts(G, wd.Winding(36, 4, 3, 9))  # the geometry was made for y = 7


def test_cutaway_removes_a_sector_of_the_stationary_parts_only():
    full = {p.key: p for p in sc.motor_parts(G, W)}
    cut = {p.key: p for p in sc.motor_parts(G, W, cutaway=True)}
    assert full.keys() == cut.keys()
    lo, hi = sc.CUT_START + 1e-3, sc.CUT_START + sc.CUT_WIDTH - 1e-3
    for k, p in cut.items():
        r = np.hypot(p.mesh.positions[:, 0], p.mesh.positions[:, 1])
        a = _angles(p.mesh)
        inside = (a > lo) & (a < hi) & (r > G.r_shaft + 1e-3)
        if p.spin is None and k not in ("terminal_box",):
            assert not inside.any(), k
            assert p.mesh.volume() < full[k].mesh.volume()
        if p.spin == "motor":
            assert np.array_equal(p.mesh.positions, full[k].mesh.positions)


def test_invalid_geometry():
    with pytest.raises(ValueError):
        replace(G, slot_depth=0.05)  # no yoke left
    with pytest.raises(ValueError):
        sc.annular_sector(0.05, 0.04, 0, 1)
    with pytest.raises(ValueError):
        sc.annular_sector(0.0, 0.04, 0, 1, 0, 7.0)
    with pytest.raises(ValueError):
        sc.box((0, 0, 0), (1, 0, 1))
    with pytest.raises(ValueError):
        sc.PowertrainLayout(wheel_radius=0.27, gear_ratio=0.5)


def test_powertrain_kinematics():
    veh = vh.demo_quadricycle(gear_ratio=7.3)
    lay = sc.demo_layout(veh)
    parts = {p.key: p for p in sc.powertrain_parts(lay, G, bt.demo_pack())}
    # centre distances = sums of the meshing radii; stage ratios multiply to G
    assert np.linalg.norm(lay.motor_axis - lay.intermediate) == pytest.approx(lay.pinion_1 + lay.gear_1)
    assert np.linalg.norm(lay.intermediate - lay.axle) == pytest.approx(lay.pinion_2 + lay.gear_2)
    assert (lay.gear_1 / lay.pinion_1) * (lay.gear_2 / lay.pinion_2) == pytest.approx(7.3)
    # the tyre has the vehicle's wheel radius about its axis (x)
    tyre = parts["wheel_fl"].mesh.positions
    assert np.max(np.hypot(tyre[:, 1], tyre[:, 2])) == pytest.approx(0.27, rel=1e-9)
    assert parts["wheel_fl"].origin[1] == pytest.approx(0.27)  # standing on the ground y = 0
    spins = {k: p.spin for k, p in parts.items()}
    assert spins["pinion_1"] == spins["motor_shaft"] == "motor" and spins["gear_1"] == "intermediate"
    assert spins["gear_2"] == spins["wheel_rr"] == spins["differential"] == "wheel"
    assert parts["battery"].facts["n_series"] == 168
    for key, path in sc.flow_paths(lay, G).items():
        pts = sc.points_along(path, [0.0, 1.0 - 1e-12])
        assert np.allclose(pts[0], path[0]) and np.allclose(pts[1], path[-1], atol=1e-9), key


@pytest.fixture(scope="module")
def chain():
    """Motor (TD5 + R1) → drive → map → vehicle → battery → thermal (2 cycles)."""
    from evlab.core import drive, losses, thermal
    from evlab.core.session import MotorParams
    from evlab.io.cycles import load_cycle
    from evlab.io.paths import data_dir

    m = MotorParams(v_phase=230.0, f_rated=50.0, pole_pairs=2, r1=0.5, r2p=2.0, x_leak=4.0, x_m=46.0,
                    r_fe=230.0, p_mech=60.0, r1_temperature_k=293.15)
    ds, st = drive.demo_settings(), losses.LossSettings()
    env = drive.envelope(m, ds)
    t, w = losses.default_grid(m, env, st, 40, 30)
    emap = losses.efficiency_map(m, t, w, ds, st, envelope=env)
    veh = vh.demo_quadricycle()
    cycle = load_cycle(data_dir() / "cycle_demo.csv")
    veh = replace(veh, gear_ratio=vh.size_vehicle(m, env, st, veh, cycle).gear_ratio)
    res = vh.simulate(cycle, veh, m, env, emap, st)
    batt = bt.simulate(bt.demo_pack(), res.p_battery, np.diff(cycle.t), 0.9)
    pc, pf = thermal.cycle_losses(res, emap)
    th = thermal.simulate(thermal.demo_thermal(), pc, pf, n_cycles=2)
    return res, cycle, veh, batt, th, emap


def test_playback_angles_and_powers_of_a_real_cycle(chain):
    res, cycle, veh, batt, th, emap = chain
    pb = sc.playback(res, cycle, veh, batt, th)
    # wheel angle = distance / wheel radius (independent: the cycle's distance), rotor angle = G × wheel angle
    assert pb.angle_wheel[-1] == pytest.approx(res.summary.distance_m / veh.wheel_radius, rel=1e-12)
    assert pb.angle_motor[-1] == pytest.approx(veh.gear_ratio * pb.angle_wheel[-1], rel=1e-12)
    # the links of the chain close the vehicle's own energy balance
    dt = np.diff(cycle.t)
    assert np.allclose(pb.p_dc + veh.aux_power, pb.p_battery)
    assert float(np.sum((pb.p_shaft - pb.p_wheel) * dt)) == pytest.approx(res.balance["gear"], rel=1e-9)
    assert float(np.sum(pb.p_friction * dt)) == pytest.approx(res.balance["friction_brake"], rel=1e-9, abs=1e-6)
    assert np.all(pb.p_friction >= -1e-9)
    # with the map: AC link = DC link − inverter losses; AC − shaft = motor losses >= 0, inverter losses >= 0
    pm = sc.playback(res, cycle, veh, emap=emap)
    moving = res.omega > 0
    assert np.all(pm.p_ac[moving] - pm.p_shaft[moving] >= -1e-6)
    assert np.all(pm.p_dc - pm.p_ac >= -1e-9) and np.array_equal(pm.p_ac[~moving], pm.p_dc[~moving])
    assert sc.frame_at(pm, cycle.t[1]).p_ac == pm.p_ac[1] and sc.frame_at(pb, cycle.t[1]).p_ac is None
    # battery and thermal series: the SOC as simulated, the last of the 2 thermal cycles
    assert np.array_equal(pb.soc, batt.soc)
    n = len(res.v)
    assert np.array_equal(pb.t_winding, th.t_w[n:]) and pb.thermal_cycle == (2, 2)
    with pytest.raises(ValueError):
        sc.playback(res, cycle, veh, replace(batt, soc=batt.soc[:-1]))


def test_frame_at_interpolates_exactly(chain):
    res, cycle, veh, batt, th, emap = chain
    pb = sc.playback(res, cycle, veh, batt, th)
    k = int(np.argmax(res.omega))
    t_mid = 0.5 * (cycle.t[k] + cycle.t[k + 1])
    f = sc.frame_at(pb, t_mid)
    assert f.omega_motor == res.omega[k] and f.torque == res.torque[k]
    assert f.angle_motor == pytest.approx(pb.angle_motor[k] + res.omega[k] * (t_mid - cycle.t[k]))
    assert f.angle_wheel == pytest.approx(f.angle_motor / veh.gear_ratio)
    # gear contact: pinion and wheel radii × angles are equal (opposite directions)
    lay = sc.demo_layout(veh)
    assert lay.pinion_1 * f.angle_motor == pytest.approx(-lay.gear_1 * f.angle_intermediate)
    assert f.soc == pytest.approx(0.5 * (batt.soc[k] + batt.soc[k + 1]))
    end = sc.frame_at(pb, cycle.t[-1])
    assert end.angle_motor == pytest.approx(pb.angle_motor[-1]) and end.t_winding == pytest.approx(th.t_w[-1])
    with pytest.raises(ValueError):
        sc.frame_at(pb, cycle.t[-1] + 1)


def test_display_rules(chain):
    res, cycle, veh, batt, _th, _emap = chain
    pb = sc.playback(res, cycle, veh)
    assert pb.soc is None and pb.t_winding is None
    for rate in (1.0, 10.0, 60.0):
        k = sc.display_slowdown(pb, rate)
        assert k >= 1 and np.max(np.abs(pb.omega_motor)) * rate / k <= sc.MAX_DISPLAY_SPEED * (1 + 1e-12)
    assert sc.flow_direction(500.0) == 1 and sc.flow_direction(-500.0) == -1 and sc.flow_direction(0.2) == 0
    assert sc.advance_flow_phase(0.5, 1e3, 1e4, 0.1) > 0.5 > sc.advance_flow_phase(0.5, -1e3, 1e4, 0.1)
    assert sc.advance_flow_phase(0.5, 0.0, 1e4, 0.1) == 0.5
    assert sc.temperature_fraction(350.0, 300.0, 400.0) == pytest.approx(0.5)
    assert sc.temperature_fraction(500.0, 300.0, 400.0) == 1.0
    with pytest.raises(ValueError):
        sc.display_slowdown(pb, 0.0)
    with pytest.raises(ValueError):
        sc.points_along([[0, 0, 0]], [0.5])
