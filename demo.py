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
    {"name": "toggle switch", "kind": "toggle switch", "position": (0.5, 0, 0)},   # new: flips, unknown
    Button("touch pad", (0.6, 0, 0), (0.05, 0.03), DOWN, None, (0.1, 1.0), None, screen_is("cursor")),  # new: no travel, no click
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


def run(open_issues=False, client=None, out_dir="unknowns", scene=scene, max_new=5):
    from button_bias import classify, diagnose, KNOWN_FAILURES, eject
    from unknowns import report_ejected, report_dark, file_reports
    work = list(scene)          # working scene; the demo's list is never changed
    eject_bin, log, reports = [], [], []
    print("IGNORED / EJECTED:")
    for orig_i, o in enumerate(list(work)):
        cat, why = classify(o)
        if cat == "button":
            continue
        name = getattr(o, "name", None) or (o.get("name") if isinstance(o, dict) else o)
        print(f"  - [{cat}] {name}: {why}")
        if cat == "unknown":
            rec = eject(work, o, eject_bin, log, from_index=orig_i)
            print(f"    {log[-1]}")
            reports.append(report_ejected(o, rec, SCENE))
    buttons, _ = perceive(work)
    cands = [Move(b.position, DOWN, 0.002, 3.0) for b in buttons]
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
                reports.append(report_dark(b, before, after, SCENE, cause))
        print(f"PRESS {b.name:6s} score={score:.2f} -> {r.upper()}  world={world}{note}")
    print(f"EJECT BIN: {[e['name'] for e in eject_bin]}")
    print(f"UNKNOWNS: {len(reports)}")
    for fp, action, where in file_reports(reports, open_issues, client, out_dir, max_new=max_new):
        print(f"  {fp} {action:11s} {where}")
    return {"work": work, "bin": eject_bin, "log": log, "reports": reports}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--open-issues", action="store_true", help="really open GitHub issues (default: dry-run)")
    ap.add_argument("--max-new", type=int, default=5, help="max new issues per run (default 5)")
    a = ap.parse_args()
    run(open_issues=a.open_issues, max_new=a.max_new)
