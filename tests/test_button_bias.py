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
    assert len(ign) == 4

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
