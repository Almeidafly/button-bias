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

def actuate(world, b, m):
    world["presses"] = world.get("presses", 0) + 1
    if effects.get(b.name):
        world["screen"] = effects[b.name]

if __name__ == "__main__":
    buttons, ignored = perceive(scene)
    print("IGNORED:")
    for n, why in ignored:
        print(f"  - {n}: {why}")
    cands = [Move(b.position, DOWN, 0.002, 3.0) for b in buttons] + [Move((0.2, 0, 0), DOWN, 0.002, 3.0)]
    world = {"screen": "off"}
    for score, b, m in choose(buttons, cands):
        r = press(world, b, m, actuate)
        print(f"PRESS {b.name:6s} score={score:.2f} -> {r.upper()}  world={world}")
