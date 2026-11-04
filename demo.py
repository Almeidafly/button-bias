from button_bias import Button, Move, perceive, choose, press

def screen_is(v):
    return lambda before, after: after.get("screen") == v and before.get("screen") != v

DOWN = (0.0, 0.0, -1.0)
scene = [
    Button("power", (0, 0, 0), (0.01, 0.01), DOWN, (0.001, 0.003), (1.0, 5.0), "click", screen_is("on")),
    Button("menu", (0.05, 0, 0), (0.01, 0.01), DOWN, (0.001, 0.003), (1.0, 5.0), "click+travel", screen_is("menu")),
    Button("stuck", (0.10, 0, 0), (0.01, 0.01), DOWN, (0.001, 0.003), (1.0, 5.0), "click", screen_is("settings")),
    Button("flat label", (0.2, 0, 0), (0.03, 0.01), None, None, None, None, None),
    "knob",
    Button("mushy (no feedback)", (0.3, 0, 0), (0.01, 0.01), DOWN, (0.001, 0.003), (1.0, 5.0), None, screen_is("x")),
    {"name": "slider", "position": (0.4, 0, 0)},
]
effects = {"power": "on", "menu": "menu", "stuck": None}  # stuck does nothing
jammed = {"stuck"}  # simulated: these buttons do not move when pushed

def actuate(world, b, m):
    """Simulated press. Returns sensor readings (travel in m, force in N)."""
    world["presses"] = world.get("presses", 0) + 1
    travel = 0.0 if b.name in jammed else m.depth
    if travel >= b.depth_range[0] and effects.get(b.name):
        world["screen"] = effects[b.name]
    return {"travel": travel, "force": m.force}

SCENE = "demo-panel-v1"


def run(open_issues=False, client=None, out_dir="unknowns", scene=scene):
    from button_bias import classify, diagnose, KNOWN_FAILURES
    from unknowns import report_ignored, report_dark, file_reports
    reports = []
    buttons, ignored = perceive(scene)
    print("IGNORED:")
    for o in scene:
        cat, why = classify(o)
        if cat == "button":
            continue
        print(f"  - [{cat}] {getattr(o, 'name', repr(o))}: {why}")
        if cat == "unknown":
            reports.append(report_ignored(o, SCENE))
    cands = [Move(b.position, DOWN, 0.002, 3.0) for b in buttons] + [Move((0.2, 0, 0), DOWN, 0.002, 3.0)]
    world = {"screen": "off"}
    for score, b, m in choose(buttons, cands):
        before = dict(world)
        after, readings = {}, {}
        def act(w, b_, m_):
            readings.update(actuate(w, b_, m_) or {}); after.update(w)
        r = press(world, b, m, act)
        note = ""
        if r == "dark":
            cause = diagnose(b, m, readings, before, after)
            note = f"  cause: {cause} (known failure, rolled back)" if cause in KNOWN_FAILURES else f"  cause: {cause}"
            if cause not in KNOWN_FAILURES:
                reports.append(report_dark(b, before, after, SCENE))
        print(f"PRESS {b.name:6s} score={score:.2f} -> {r.upper()}  world={world}{note}")
    print(f"UNKNOWNS: {len(reports)}")
    for fp, action, where in file_reports(reports, open_issues, client, out_dir):
        print(f"  {fp} {action:8s} {where}")


if __name__ == "__main__":
    import sys
    run(open_issues="--open-issues" in sys.argv)
