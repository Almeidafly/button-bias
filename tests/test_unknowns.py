import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
import demo, unknowns
from button_bias import Button, eject, classify
from unknowns import file_reports, report_ejected, fingerprint, object_kind, bad_fields, REPO


class FakeGh:
    def __init__(self, repo=REPO):
        self.repo = repo; self.issues = []; self.created = 0
    def ensure_labels(self): pass
    def all_issues(self): return [dict(i) for i in self.issues]
    def get_issue(self, url): return next((dict(i) for i in self.issues if i["url"] == url), None)
    def search(self, fp): return [dict(i) for i in self.issues if fp in i["body"]]
    def create_issue(self, t, body):
        n = len(self.issues) + 1
        url = f"https://github.com/{self.repo}/issues/{n}"
        self.issues.append({"number": n, "state": "OPEN", "title": t, "body": body, "url": url})
        self.created += 1; return url


class LaggyGh(FakeGh):
    """List and search never show new issues (index lag); only direct reads work."""
    def all_issues(self): return []
    def search(self, fp): return []


def _rep(obj, scene="s"):
    return report_ejected(obj, {"name": "x", "from_index": 0, "from_position": None, "bin_slot": 0}, scene)


# ---- eject ----

def test_unknowns_are_ejected_never_pressed(tmp_path):
    pressed = []
    orig = demo.actuate
    demo.actuate = lambda w, b, m: (pressed.append(b.name), orig(w, b, m))[1]
    try:
        out = demo.run(out_dir=str(tmp_path))
    finally:
        demo.actuate = orig
    names = [e["name"] for e in out["bin"]]
    assert names == ["toggle switch", "touch pad"]
    assert not any(e["object"] in out["work"] for e in out["bin"])
    assert "touch pad" not in pressed and "toggle switch" not in pressed
    assert [e["from_index"] for e in out["bin"]] == [7, 8]
    assert len(out["log"]) == 2 and all(l.startswith("EJECTED") for l in out["log"])
    assert len(demo.scene) == 9  # the demo scene itself is not changed


def test_known_things_are_not_ejected(tmp_path):
    out = demo.run(out_dir=str(tmp_path))
    for o in demo.scene[:7]:
        assert classify(o)[0] != "unknown"
        assert all(e["object"] is not o for e in out["bin"])


def test_eject_records_where():
    work, b, log = ["a", "knob", "b"], [], []
    rec = eject(work, "knob", b, log)
    assert work == ["a", "b"] and rec["from_index"] == 1 and rec["bin_slot"] == 0


# ---- issues ----

def test_dry_run_default_no_issues(tmp_path, monkeypatch):
    monkeypatch.setattr(unknowns, "GhClient", lambda *a: pytest.fail("no client in dry-run"))
    demo.run(out_dir=str(tmp_path))
    assert len(list(tmp_path.glob("bb2-*.md"))) == 2
    assert not (tmp_path / "opened.json").exists()


def test_eject_pushes_one_issue_each_with_labels(tmp_path):
    fake = FakeGh()
    demo.run(open_issues=True, client=fake, out_dir=str(tmp_path))
    assert fake.created == 2
    assert all("ejected" in i["body"] and "bin slot" in i["body"] for i in fake.issues)
    assert unknowns.LABELS == ("unknown", "ejected")
    led = json.load(open(tmp_path / "opened.json"))
    assert len(led) == 2


def test_rerun_no_dupes(tmp_path):
    fake = FakeGh()
    demo.run(open_issues=True, client=fake, out_dir=str(tmp_path))
    demo.run(open_issues=True, client=fake, out_dir=str(tmp_path))
    assert fake.created == 2


def test_closed_issue_is_seen_before_not_reopened(tmp_path, capsys):
    fake = FakeGh()
    demo.run(open_issues=True, client=fake, out_dir=str(tmp_path))
    for i in fake.issues:
        i["state"] = "CLOSED"
    capsys.readouterr()
    demo.run(open_issues=True, client=fake, out_dir=str(tmp_path / "fresh"))  # no ledger
    assert fake.created == 2
    assert "seen before (closed #1)" in capsys.readouterr().out


def test_ledger_dedupes_when_list_and_search_lag(tmp_path):
    fake = LaggyGh()
    demo.run(open_issues=True, client=fake, out_dir=str(tmp_path))
    demo.run(open_issues=True, client=fake, out_dir=str(tmp_path))
    assert fake.created == 2


def test_search_fallback_without_ledger(tmp_path):
    class SearchOnly(FakeGh):
        def all_issues(self): return []
    fake = SearchOnly()
    demo.run(open_issues=True, client=fake, out_dir=str(tmp_path / "a"))
    demo.run(open_issues=True, client=fake, out_dir=str(tmp_path / "b"))
    assert fake.created == 2


def test_cap_limits_new_issues(tmp_path):
    reps = [_rep(f"thing-{i}") for i in range(8)]
    fake = FakeGh()
    res = file_reports(reps, True, fake, str(tmp_path))
    assert fake.created == 5
    assert [a for _, a, _ in res].count("capped") == 3
    fake2 = FakeGh()
    file_reports(reps, True, fake2, str(tmp_path / "b"), max_new=1)
    assert fake2.created == 1
    assert len(list(tmp_path.glob("bb2-*.md"))) == 8  # capped ones still written


# ---- fingerprint ----

def test_moving_a_thing_is_not_a_new_unknown():
    a = {"name": "toggle switch", "kind": "toggle switch", "position": (0.5, 0, 0)}
    b = dict(a, position=(9, 9, 9))
    assert _rep(a, "scene-1")["fingerprint"] == _rep(b, "scene-2")["fingerprint"]
    t = demo.scene[8]
    from dataclasses import replace
    assert _rep(t)["fingerprint"] == _rep(replace(t, position=(1, 2, 3)))["fingerprint"]


def test_fingerprint_changes_with_kind_or_failed_fields():
    t = demo.scene[8]
    from dataclasses import replace
    assert _rep(t)["fingerprint"] != _rep(replace(t, feedback="click"))["fingerprint"]
    assert _rep("thing-1")["fingerprint"] != _rep("thing-2")["fingerprint"]


def test_bad_fields_listed():
    assert set(bad_fields(demo.scene[8])) == {"depth_range", "feedback"}
    assert "position" in bad_fields("knob")


@pytest.mark.parametrize("repo", ["someone/else", "Almeidafly/limb-trees", "almeidafly/button-bias-x"])
def test_repo_locked(tmp_path, repo):
    with pytest.raises(ValueError):
        file_reports([_rep("x")], True, FakeGh(), str(tmp_path), repo=repo)
    with pytest.raises(ValueError):
        file_reports([_rep("x")], True, FakeGh(repo), str(tmp_path))
    with pytest.raises(ValueError):
        unknowns.GhClient(repo)
