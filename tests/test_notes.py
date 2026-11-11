"""io.notes: the démo labels shared by the GUI chips and the reports."""

from dataclasses import replace

from evlab.core import drive, losses, thermal, vehicle
from evlab.core.session import td5_ex1
from evlab.io.notes import demo_labels


def test_nothing_given_nothing_demo():
    assert demo_labels() == []
    assert demo_labels(motor=td5_ex1()) == []  # course data, not démo


def test_drive_settings_a16_per_field():
    lab = demo_labels(drive_settings=drive.demo_settings())
    assert lab == ["réglages variateur I max, boost, marge, f max (A16)"]
    assert demo_labels(drive_settings=replace(drive.demo_settings(), i_max=35.0)) == [
        "réglages variateur boost, marge, f max (A16)"]
    assert demo_labels(drive_settings=drive.DriveSettings(35.0, 5.0, 0.9, 120.0)) == []


def test_inverter_a21_and_beta_a19():
    st = losses.LossSettings()
    assert demo_labels(loss_settings=st) == ["pertes onduleur (A21)"]
    assert demo_labels(loss_settings=st, include_beta=True) == ["pertes onduleur (A21)", "β = 1,5 (A19)"]
    assert demo_labels(loss_settings=replace(st, inverter=False, beta=2.0), include_beta=True) == []


def test_thermal_a26_per_field_and_vehicle():
    p = replace(thermal.demo_thermal(), c_w=4000.0)
    assert demo_labels(thermal_params=p) == ["réseau thermique C_s, R_ws, R_sa (A26)"]
    veh = vehicle.demo_quadricycle()
    assert demo_labels(vehicle=veh) == [veh.name]
    assert demo_labels(vehicle=replace(veh, is_demo=False)) == []


def test_demo_motor():
    m = replace(td5_ex1(), is_demo=True, source="TP3 démo")
    assert demo_labels(motor=m) == ["moteur identifié sur des essais synthétiques (TP3 démo)"]
