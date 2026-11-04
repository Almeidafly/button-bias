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

## What it learned (v0.3.0)
The robot now sorts every object into one of four groups:
- **button** – a real button. It may press it.
- **known non-button** – something it has learned is not a button: a flat label (no press axis, no travel), a knob (turns, doesn't press), a slider (slides, wherever it sits). Ignored quietly, never reported.
- **defect** – a button that is complete except it gives no click or travel. Known problem. It is **not pressed**, because without feedback the robot can't tell a press happened.
- **unknown** – anything else. Only these become reports/issues.

A **dark** press is now diagnosed from (simulated) sensor readings of travel and force:
`stuck / no travel`, `force out of range`, `travel but no result`, or `wrong result`. These are known failures: rolled back and logged, not reported. Only a dark press with missing readings (`unexplained`) becomes an unknown.

The demo now prints `UNKNOWNS: 0`.

## Eject what it doesn't know (v0.4.0)
Anything that is not a button, not a known non-button and not a known defect is **unknown**. The robot **ejects** it: it takes it out of the working scene and puts it in an eject bin, noting where it was (scene slot and position). It never presses or touches an unknown in any other way. Ejection is simulated and logged.

Every ejection pushes one issue (labels `unknown` + `ejected`) saying what was ejected, which Button fields failed, and where it went. Rules:
- **Only in Almeidafly/button-bias.** Other repos are refused in code.
- **Dry-run by default.** Real issues need `--open-issues`.
- **No duplicates.** The fingerprint is the object's kind + its failed fields. Position, scene and time are left out, so moving a toggle switch is not a new unknown. Before opening, it checks the committed ledger `unknowns/opened.json`, every issue (open **and** closed), and GitHub search. A closed match is skipped and logged `seen before (closed #N)`; it is not reopened or commented on.
- **Cap.** At most 5 new issues per run (`--max-new N`). The rest stay as files in `unknowns/`.

The demo has two new unknowns, a toggle switch and a touch pad (no travel range, no click). Both are ejected and each got one issue: #7, #8.

## Run
```
pip install numpy pytest
python demo.py                 # dry-run, writes unknowns/
python demo.py --open-issues   # real issues in Almeidafly/button-bias
python demo.py --open-issues --max-new 2
pytest -q
```

## Honest caveats
- The "world" is a dict; "pressing" is a function we wrote. Real perception would need to fill these fields from sensors, which is the hard part and is not here.
- Rollback restores our state; a real press cannot be undone.
- Dedupe uses the committed ledger, the issue list and search. If two machines run at the same moment before either pushes its ledger, a duplicate is still possible (happened once in v0.2.0: #6 duplicated #5).
- Two different unknown things with the same kind name and the same failed fields share one fingerprint, so only the first gets an issue.
- v0.4.0 fingerprints (`bb2-`) differ from v0.2.0 (`bb-`); old issues #1-#6 are all closed and their objects are now known, so this doesn't matter today.
- Knob and slider are recognised by their kind/name, not by shape. A knob called something else is still unknown.
- Sensor readings are made up by the demo; real travel/force sensing is not here.
- Candidate moves are hand-made, not planned. Thresholds (5 mm lateral) are guesses.

Related: [limb-trees](https://github.com/Almeidafly/limb-trees).
