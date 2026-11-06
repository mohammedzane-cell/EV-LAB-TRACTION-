import math

import pytest

from evlab.core.session import MotorParams, Session, td5_ex1


def test_td5_ex1_values():
    m = td5_ex1()
    assert m.v_phase == 230.0
    assert m.f_rated == 50.0
    assert m.pole_pairs == 2
    assert m.r_fe == 230.0
    assert m.x_m == 46.0
    assert m.x_leak == 4.0
    assert m.r2p == 2.0
    assert m.r1 == 0.0
    assert m.source == "TD5 Ex 1"


def test_derived_quantities():
    m = td5_ex1()
    assert m.omega_rated == pytest.approx(2 * math.pi * 50)
    assert m.omega_sync == pytest.approx(2 * math.pi * 50 / 2)
    assert m.l_leak == pytest.approx(4.0 / (2 * math.pi * 50))
    assert m.l_m == pytest.approx(46.0 / (2 * math.pi * 50))


def test_params_are_immutable():
    m = td5_ex1()
    with pytest.raises(AttributeError):
        m.r2p = 3.0  # type: ignore[misc]


@pytest.mark.parametrize(
    "field, value",
    [
        ("v_phase", 0.0),
        ("v_phase", -1.0),
        ("f_rated", 0.0),
        ("r2p", 0.0),
        ("x_leak", 0.0),
        ("x_m", -5.0),
        ("r_fe", 0.0),
        ("r1", -0.1),
        ("v_phase", math.nan),
        ("r1", math.inf),
    ],
)
def test_invalid_values_raise(field, value):
    kwargs = dict(
        v_phase=230.0, f_rated=50.0, pole_pairs=2, r1=0.0,
        r2p=2.0, x_leak=4.0, x_m=46.0, r_fe=230.0,
    )
    kwargs[field] = value
    with pytest.raises(ValueError, match=field):
        MotorParams(**kwargs)


@pytest.mark.parametrize("p", [0, -1, 1.5])
def test_invalid_pole_pairs(p):
    with pytest.raises(ValueError, match="pole_pairs"):
        MotorParams(
            v_phase=230.0, f_rated=50.0, pole_pairs=p, r1=0.0,
            r2p=2.0, x_leak=4.0, x_m=46.0, r_fe=230.0,
        )


def test_session_defaults_to_td5_and_can_be_replaced():
    s = Session()
    assert s.motor == td5_ex1()
    new = MotorParams(
        v_phase=220.0, f_rated=50.0, pole_pairs=2, r1=0.5,
        r2p=1.0, x_leak=3.0, x_m=40.0, r_fe=300.0, source="TP3",
    )
    s.set_motor(new)
    assert s.motor is new


def test_session_rejects_non_motor():
    s = Session()
    with pytest.raises(ValueError, match="MotorParams"):
        s.set_motor("not a motor")  # type: ignore[arg-type]


def test_layout_default_and_validation():
    assert td5_ex1().layout == "tp3"
    kwargs = dict(v_phase=230.0, f_rated=50.0, pole_pairs=2, r1=0.0,
                  r2p=2.0, x_leak=4.0, x_m=46.0, r_fe=230.0)
    assert MotorParams(**kwargs, layout="terminals").layout == "terminals"
    with pytest.raises(ValueError, match="layout"):
        MotorParams(**kwargs, layout="T")
