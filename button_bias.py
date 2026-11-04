"""Button bias: a robot that only cares about real buttons. Simulation only."""
from dataclasses import dataclass, field
from typing import Callable, Optional, Any
import numpy as np

FEEDBACK = {"click", "travel", "click+travel"}


@dataclass
class Button:
    name: str
    position: Optional[tuple] = None        # (x, y, z) metres
    size: Optional[tuple] = None            # (w, h) metres, both > 0
    press_axis: Optional[tuple] = None      # unit vector the button moves along
    depth_range: Optional[tuple] = None     # (min, max) metres of travel to register
    force_range: Optional[tuple] = None     # (min, max) newtons to register
    feedback: Optional[str] = None          # "click", "travel" or "click+travel"
    expected: Optional[Callable[[dict, dict], bool]] = None  # check(before, after)


def _vec(v, n):
    return isinstance(v, (tuple, list)) and len(v) == n and all(
        isinstance(a, (int, float)) and np.isfinite(a) for a in v)


def _range(r):
    return _vec(r, 2) and 0 < r[0] < r[1]


def why_not_button(obj: Any) -> Optional[str]:
    """Return None if obj is exactly a button, else the reason it is ignored."""
    if not isinstance(obj, Button):
        return f"not a Button (is {type(obj).__name__})"
    if not _vec(obj.position, 3):
        return "missing/invalid position"
    if not _vec(obj.size, 2) or min(obj.size) <= 0:
        return "missing/invalid size"
    if not _vec(obj.press_axis, 3) or abs(np.linalg.norm(obj.press_axis) - 1) > 1e-6:
        return "missing/invalid press axis (needs unit vector)"
    if not _range(obj.depth_range):
        return "missing/invalid press depth range"
    if not _range(obj.force_range):
        return "missing/invalid force range"
    if obj.feedback not in FEEDBACK:
        return "missing/invalid travel/click feedback"
    if not callable(obj.expected):
        return "missing expected result check"
    return None


def is_button(obj: Any) -> bool:
    return why_not_button(obj) is None


def perceive(scene):
    """Keep buttons, ignore everything else. Returns (buttons, ignored_log)."""
    buttons, ignored = [], []
    for obj in scene:
        reason = why_not_button(obj)
        if reason is None:
            buttons.append(obj)
        else:
            ignored.append((getattr(obj, "name", repr(obj)), reason))
    return buttons, ignored


@dataclass
class Move:
    target: tuple      # fingertip end point
    direction: tuple   # push direction (unit)
    depth: float
    force: float


def bias_score(move: Move, obj: Any, tol: float = 0.005) -> float:
    """1.0-ish for a move that ends on a real button's press axis within depth and force; 0 otherwise."""
    if not is_button(obj):
        return 0.0
    p = np.array(obj.position, float); a = np.array(obj.press_axis, float)
    t = np.array(move.target, float); d = np.array(move.direction, float)
    off = t - p
    lateral = np.linalg.norm(off - off.dot(a) * a)
    if lateral > min(obj.size) / 2 or lateral > tol:
        return 0.0
    if np.linalg.norm(d) == 0 or np.dot(d / np.linalg.norm(d), a) < 0.99:
        return 0.0
    if not (obj.depth_range[0] <= move.depth <= obj.depth_range[1]):
        return 0.0
    if not (obj.force_range[0] <= move.force <= obj.force_range[1]):
        return 0.0
    return float(1.0 - lateral / tol * 0.5)  # in (0.5, 1]


def press(world: dict, button: Button, move: Move, actuate: Callable[[dict, Button, Move], None]):
    """Lit/dark test. Snapshot, act, check expected result. Dark rolls back."""
    snapshot = dict(world)
    actuate(world, button, move)
    lit = bool(button.expected(snapshot, world))
    if not lit:
        world.clear(); world.update(snapshot)
    return "lit" if lit else "dark"


def choose(buttons, candidates):
    """Best (score, button, move) per button; buttons with no scoring move are skipped."""
    out = []
    for b in buttons:
        best = max(((bias_score(m, b), m) for m in candidates), key=lambda x: x[0], default=(0, None))
        if best[0] > 0:
            out.append((best[0], b, best[1]))
    return out


# ---- v0.3.0: things the robot now KNOWS are not buttons (ignored silently, never "unknown") ----

def _kind(obj):
    """Best-effort kind name for an object: .kind / ['kind'] / ['name'] / the string itself."""
    if isinstance(obj, str):
        return obj.strip().lower()
    if isinstance(obj, dict):
        return str(obj.get("kind") or obj.get("name") or "").strip().lower()
    return str(getattr(obj, "kind", "") or "").strip().lower()


def _is_flat_label(obj):
    # Has a place and a size, but nothing that moves: no axis, depth, force, feedback or result.
    return (isinstance(obj, Button) and _vec(obj.position, 3) and _vec(obj.size, 2)
            and all(getattr(obj, f) is None for f in
                    ("press_axis", "depth_range", "force_range", "feedback", "expected")))


def _is_knob(obj):
    # A knob turns; it has no straight-line press axis.
    return _kind(obj) in {"knob", "dial", "rotary knob"}


def _is_slider(obj):
    # A slider moves sideways along a track; its position does not matter.
    return _kind(obj) in {"slider", "fader"}


# name -> (match rule, reason)
KNOWN_NON_BUTTONS = {
    "flat_label": (_is_flat_label, "flat printed label: has position and size but no press axis, travel, force, feedback or result"),
    "knob": (_is_knob, "knob: turns around an axis instead of pressing along one"),
    "slider": (_is_slider, "slider: slides along a track instead of pressing in"),
}


def classify(obj):
    """Return (category, reason). category is one of:
    'button', 'known_non_button', 'defect', 'unknown'."""
    reason = why_not_button(obj)
    if reason is None:
        return "button", "valid button"
    defect = known_defect(obj)
    if defect:
        return "defect", defect
    for name, (rule, why) in KNOWN_NON_BUTTONS.items():
        if rule(obj):
            return "known_non_button", f"{name}: {why}"
    return "unknown", reason


def known_defect(obj):
    """A button that is complete except for feedback: a known defect. Never pressed
    (without click/travel feedback the robot cannot tell a press happened), never unknown."""
    if isinstance(obj, Button) and obj.feedback not in FEEDBACK:
        from dataclasses import replace
        if is_button(replace(obj, feedback="click")):
            return "button missing feedback: known defect, not pressed (cannot confirm a press without click/travel)"
    return None


# ---- dark press diagnosis from (simulated) sensor readings ----
KNOWN_FAILURES = {
    "force out of range": "pushed harder or softer than the button's force range",
    "stuck / no travel": "button did not move far enough to register",
    "travel but no result": "button moved, but nothing changed",
    "wrong result": "something changed, but not what the button promises",
}


def diagnose(button, move, readings, before, after):
    """Name the likely cause of a dark press. readings = {'travel': m, 'force': N}.
    Returns one of KNOWN_FAILURES keys, or 'unexplained' if readings are missing."""
    if not readings or "travel" not in readings or "force" not in readings:
        return "unexplained"
    lo, hi = button.force_range
    if not (lo <= readings["force"] <= hi):
        return "force out of range"
    if readings["travel"] < button.depth_range[0]:
        return "stuck / no travel"
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k) and k != "presses"}
    if not changed:
        return "travel but no result"
    return "wrong result"


# ---- v0.4.0: eject what it does not know ----

def eject(scene, obj, bin_, log, from_index=None):
    """Simulated ejection: take an unknown object out of the working scene into the eject bin.
    The object is never pressed or touched in any other way. Returns the bin record."""
    idx = next(i for i, o in enumerate(scene) if o is obj)
    where = getattr(obj, "position", None) if not isinstance(obj, dict) else obj.get("position")
    scene.pop(idx)
    rec = {"object": obj, "name": str(getattr(obj, "name", None) or (obj.get("name") if isinstance(obj, dict) else obj)),
           "from_index": idx if from_index is None else from_index, "from_position": where, "bin_slot": len(bin_)}
    bin_.append(rec)
    log.append(f"EJECTED {rec['name']!r} from slot {rec['from_index']} (position {where}) -> eject bin slot {rec['bin_slot']}")
    return rec
