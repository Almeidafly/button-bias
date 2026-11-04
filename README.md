# button-bias

A robot that is biased toward buttons. It knows exactly what a button is, and ignores everything else.

**Simulation only.** No real robot, camera, or force sensor is involved. Everything here is plain Python data.

## What counts as a button
A `Button` must have *all* of these, and each must be valid:
- position (x, y, z)
- size (width, height, both above zero)
- press axis (a unit vector – the direction it moves)
- press depth range (min < max)
- required force range (min < max)
- feedback: `click`, `travel`, or `click+travel`
- an expected result: a check that says what should change (for example, the screen turns on)

If any one is missing or wrong, it is not a button. A flat label, a knob, a slider, or a button with no feedback is ignored, and the reason is logged.

## How it acts
1. **Perceive**: drop every non-button, log why.
2. **Bias score**: a move only scores above zero if it ends on a real button's press axis, pushes along that axis, and stays inside the depth and force ranges. Anything else scores zero.
3. **Lit/dark test**: snapshot the world, press, check the expected result. **Lit** = the expected thing happened. **Dark** = it didn't, so the world rolls back to the snapshot.

## What it doesn't know becomes an issue (v0.2.0)
Everything the robot ignores, and every **dark** press it can't explain, becomes an *unknown report*: what it saw, which Button fields were missing or invalid, the scene name, and a timestamp.

- **Default is dry-run.** Reports are written to `unknowns/` as `.json` and `.md`. Nothing goes to GitHub.
- `python demo.py --open-issues` opens real issues, labelled `unknown`, **only in Almeidafly/button-bias**. Any other repo is refused in code.
- **No duplicates.** Each report has a stable fingerprint (same thing, same scene = same fingerprint, whatever the time). Before opening, it checks open `unknown` issues for that fingerprint in the body. It also keeps a local note (`unknowns/opened.json`) of what it already opened, because GitHub's issue list can lag a few seconds behind.
- A **lit** press is known, so it never makes a report.

## Run
```
pip install numpy pytest
python demo.py                 # dry-run, writes unknowns/
python demo.py --open-issues   # real issues in Almeidafly/button-bias
pytest -q
```

## Honest caveats
- The "world" is a dict; "pressing" is a function we wrote. Real perception would need to fill these fields from sensors, which is the hard part and is not here.
- Rollback restores our state; a real press cannot be undone.
- Dedupe uses the issue list plus a local note. On a fresh machine with no note, an issue opened seconds earlier may be missed and duplicated (this happened once: #6 duplicates #5).
- Closed issues are not counted, so a closed unknown that shows up again gets a new issue.
- Candidate moves are hand-made, not planned. Thresholds (5 mm lateral) are guesses.

Related: [limb-trees](https://github.com/Almeidafly/limb-trees).
