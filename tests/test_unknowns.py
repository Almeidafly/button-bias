import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
import demo, unknowns
from button_bias import Button

# A scene with things the robot still does not know.
MYSTERY = demo.scene[:2] + ["thing-1", {"name": "blob"}, Button("half", (0, 0, 0), (0.01, 0.01), (0, 0, -1), None, (1, 2), "click", lambda a, b: True)]
from unknowns import file_reports, report_ignored, REPO


class FakeGh:
    def __init__(self, repo=REPO):
        self.repo = repo; self.issues = []; self.labels = 0
    def ensure_label(self): self.labels += 1
    def open_issue_bodies(self): return [dict(i) for i in self.issues]
    def issue_body_if_open(self, url):
        return next((i["body"] for i in self.issues if i["url"] == url), None)
    def create_issue(self, t, body):
        url = f"https://github.com/{self.repo}/issues/{len(self.issues)+1}"
        self.issues.append({"title": t, "body": body, "url": url}); return url


def test_dry_run_default_writes_files_no_issues(tmp_path, monkeypatch):
    monkeypatch.setattr(unknowns, "GhClient", lambda *a: pytest.fail("no client in dry-run"))
    fake = FakeGh()
    demo.run(out_dir=str(tmp_path), client=fake, scene=MYSTERY)
    assert fake.issues == []
    assert len(list(tmp_path.glob("*.md"))) == 3 and len(list(tmp_path.glob("bb-*.json"))) == 3


def test_open_issues_and_dedupe(tmp_path):
    fake = FakeGh()
    demo.run(open_issues=True, client=fake, out_dir=str(tmp_path), scene=MYSTERY)
    assert len(fake.issues) == 3
    assert all("bb-" in i["body"] for i in fake.issues)
    demo.run(open_issues=True, client=fake, out_dir=str(tmp_path), scene=MYSTERY)
    assert len(fake.issues) == 3


def test_duplicate_reports_in_one_batch(tmp_path):
    r = report_ignored("knob", "s")
    fake = FakeGh()
    res = file_reports([r, report_ignored("knob", "s")], True, fake, str(tmp_path))
    assert len(fake.issues) == 1 and len(res) == 1


def test_fingerprint_stable_across_time():
    from datetime import datetime, timezone
    a = report_ignored("knob", "s", datetime(2020, 1, 1, tzinfo=timezone.utc))
    b = report_ignored("knob", "s")
    assert a["fingerprint"] == b["fingerprint"] and a["timestamp"] != b["timestamp"]


@pytest.mark.parametrize("repo", ["someone/else", "Almeidafly/limb-trees", "almeidafly/button-bias-x"])
def test_repo_locked(tmp_path, repo):
    with pytest.raises(ValueError):
        file_reports([report_ignored("knob", "s")], True, FakeGh(), str(tmp_path), repo=repo)
    with pytest.raises(ValueError):
        file_reports([report_ignored("knob", "s")], True, FakeGh(repo), str(tmp_path))
    with pytest.raises(ValueError):
        unknowns.GhClient(repo)


def test_bad_fields_listed():
    r = report_ignored(demo.scene[3], "s")
    assert set(r["bad_fields"]) == {"press_axis", "depth_range", "force_range", "feedback", "expected"}
    assert report_ignored(demo.scene[5], "s")["bad_fields"] == ["feedback"]
    assert "position" in report_ignored("knob", "s")["bad_fields"]


class LaggyGh(FakeGh):
    """List API never shows new issues (search-index lag)."""
    def open_issue_bodies(self): return []


def test_dedupe_survives_list_lag(tmp_path):
    fake = LaggyGh()
    demo.run(open_issues=True, client=fake, out_dir=str(tmp_path), scene=MYSTERY)
    demo.run(open_issues=True, client=fake, out_dir=str(tmp_path), scene=MYSTERY)
    assert len(fake.issues) == 3
