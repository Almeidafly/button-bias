import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dataclasses import replace
import pytest
from button_bias import Button, Move, is_button, perceive, bias_score, press
import demo

GOOD = demo.scene[0]

def test_real_button_accepted():
    assert is_button(GOOD)

@pytest.mark.parametrize("obj", ["knob", 42, None, {"position": (0, 0, 0)}, demo.scene[3], demo.scene[5]])
def test_non_buttons_always_ignored(obj):
    assert not is_button(obj)
    btns, ign = perceive([obj])
    assert btns == [] and len(ign) == 1

@pytest.mark.parametrize("field,val", [("position", None), ("size", (0, 0.01)), ("press_axis", (0, 0, -2)),
    ("depth_range", (0.003, 0.001)), ("force_range", None), ("feedback", "beep"), ("expected", "yes")])
def test_near_misses_rejected(field, val):
    assert not is_button(replace(GOOD, **{field: val}))

def test_scene_filter():
    btns, ign = perceive(demo.scene)
    assert [b.name for b in btns] == ["power", "menu", "stuck"]
    assert len(ign) == 6

def test_bias_zero_for_non_buttons_and_bad_moves():
    m = Move(GOOD.position, demo.DOWN, 0.002, 3.0)
    assert bias_score(m, GOOD) > 0
    assert bias_score(m, "knob") == 0 and bias_score(m, demo.scene[3]) == 0
    assert bias_score(Move((0.02, 0, 0), demo.DOWN, 0.002, 3.0), GOOD) == 0
    assert bias_score(Move(GOOD.position, (1, 0, 0), 0.002, 3.0), GOOD) == 0
    assert bias_score(Move(GOOD.position, demo.DOWN, 0.01, 3.0), GOOD) == 0
    assert bias_score(Move(GOOD.position, demo.DOWN, 0.002, 50.0), GOOD) == 0

def test_lit_press():
    w = {"screen": "off"}
    assert press(w, GOOD, Move(GOOD.position, demo.DOWN, 0.002, 3.0), demo.actuate) == "lit"
    assert w["screen"] == "on"

def test_dark_press_rolls_back():
    stuck = demo.scene[2]
    w = {"screen": "off"}
    assert press(w, stuck, Move(stuck.position, demo.DOWN, 0.002, 3.0), demo.actuate) == "dark"
    assert w == {"screen": "off"}


from button_bias import classify

def test_flat_label_is_known_non_button():
    assert classify(demo.scene[3])[0] == "known_non_button"

def test_real_buttons_classified_button():
    assert all(classify(b)[0] == "button" for b in demo.scene[:3])


def test_knob_is_known_non_button():
    for k in ["knob", "Knob ", {"kind": "dial"}]:
        assert classify(k)[0] == "known_non_button"


def test_slider_is_known_non_button_wherever_it_is():
    for x in [0.0, 0.4, 9.9]:
        assert classify({"name": "slider", "position": (x, 0, 0)})[0] == "known_non_button"


def test_mushy_is_known_defect_and_never_pressed():
    cat, why = classify(demo.scene[5])
    assert cat == "defect" and "missing feedback" in why
    assert demo.scene[5] not in perceive(demo.scene)[0]

def test_defect_only_when_feedback_is_the_only_problem():
    assert classify(replace(GOOD, feedback=None, force_range=None))[0] == "unknown"


from button_bias import diagnose, Move as _M

def _d(readings, before={"screen": "a"}, after={"screen": "a"}):
    return diagnose(GOOD, _M(GOOD.position, demo.DOWN, 0.002, 3.0), readings, before, after)

def test_diagnosis_causes():
    assert _d({"travel": 0.0, "force": 3.0}) == "stuck / no travel"
    assert _d({"travel": 0.002, "force": 50.0}) == "force out of range"
    assert _d({"travel": 0.002, "force": 3.0}) == "travel but no result"
    assert _d({"travel": 0.002, "force": 3.0}, after={"screen": "b"}) == "wrong result"
    assert _d({}) == "unexplained"

def test_original_demo_objects_have_zero_unknowns(tmp_path, capsys):
    fake = type("F", (), {"repo": "Almeidafly/button-bias"})()
    demo.run(out_dir=str(tmp_path), client=fake, scene=demo.scene[:7])
    out = capsys.readouterr().out
    assert "UNKNOWNS: 0" in out and "stuck / no travel" in out and "[unknown]" not in out
