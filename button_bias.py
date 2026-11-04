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
