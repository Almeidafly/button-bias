"""Turn everything the robot doesn't know into 'unknown' reports, and (optionally) GitHub issues.

Issues are only ever opened in Almeidafly/button-bias. Default is dry-run: files in unknowns/.
"""
import hashlib, json, os, subprocess
from dataclasses import fields as dc_fields
from datetime import datetime, timezone
from button_bias import Button, why_not_button

REPO = "Almeidafly/button-bias"
LABEL = "unknown"


def _describe(obj):
    if isinstance(obj, Button):
        return {f.name: (repr(getattr(obj, f.name)) if not callable(getattr(obj, f.name)) else "<check fn>")
                for f in dc_fields(obj)}
    return {"type": type(obj).__name__, "repr": repr(obj)}


def bad_fields(obj):
    """Every Button field that is missing or invalid (all of them if obj isn't a Button)."""
    names = [f.name for f in dc_fields(Button) if f.name != "name"]
    if not isinstance(obj, Button):
        return names
    out = []
    for n in names:
        good = {k: getattr(obj, k) for k in names}
        ok_ref = Button("ref", (0, 0, 0), (1, 1), (0, 0, 1), (1, 2), (1, 2), "click", lambda a, b: True)
        probe = Button("probe", **{k: getattr(ok_ref, k) for k in names})
        setattr(probe, n, good[n])
        if why_not_button(probe) is not None:
            out.append(n)
    return out


def fingerprint(kind, name, reason, scene):
    raw = json.dumps([kind, str(name), reason, scene])
    return "bb-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def report_ignored(obj, scene, now=None):
    name = getattr(obj, "name", repr(obj))
    reason = why_not_button(obj)
    return _report("ignored", name, reason, scene, _describe(obj), bad_fields(obj), now)


def report_dark(button, before, after, scene, now=None):
    reason = "dark press: expected result did not happen, cause unknown"
    seen = {"before": before, "after_press": after, "button": _describe(button)}
    return _report("dark-press", button.name, reason, scene, seen, [], now)


def _report(kind, name, reason, scene, seen, bad, now):
    return {"fingerprint": fingerprint(kind, name, reason, scene), "kind": kind, "name": str(name),
            "reason": reason, "bad_fields": bad, "seen": seen, "scene": scene,
            "timestamp": (now or datetime.now(timezone.utc)).isoformat()}


def to_markdown(r):
    return (f"The robot does not know this thing.\n\n- **kind:** {r['kind']}\n- **name:** `{r['name']}`\n"
            f"- **reason:** {r['reason']}\n- **missing/invalid Button fields:** {', '.join(r['bad_fields']) or 'none'}\n"
            f"- **scene:** {r['scene']}\n- **first seen:** {r['timestamp']}\n\n"
            f"What it saw:\n```json\n{json.dumps(r['seen'], indent=2, default=str)}\n```\n\n"
            f"fingerprint: `{r['fingerprint']}`\n\n_Simulation only. Opened by button-bias._\n")


def title(r):
    return f"[unknown] {r['kind']}: {r['name'][:60]} ({r['reason'][:60]})"


class GhClient:
    """Real client using the gh CLI. Locked to REPO."""
    def __init__(self, repo=REPO):
        _check_repo(repo); self.repo = repo

    def _gh(self, *args):
        return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout

    def ensure_label(self):
        subprocess.run(["gh", "label", "create", LABEL, "--repo", self.repo, "--color", "888888",
                        "--description", "Something the robot does not know"], capture_output=True)

    def open_issue_bodies(self):
        out = self._gh("issue", "list", "--repo", self.repo, "--state", "open", "--label", LABEL,
                       "--limit", "1000", "--json", "number,body,url")
        return json.loads(out)

    def issue_body_if_open(self, url):
        """Direct read of one issue (not the search index, which can lag)."""
        try:
            d = json.loads(self._gh("issue", "view", url, "--repo", self.repo, "--json", "state,body"))
        except subprocess.CalledProcessError:
            return None
        return d["body"] if d["state"] == "OPEN" else None

    def create_issue(self, t, body):
        return self._gh("issue", "create", "--repo", self.repo, "--title", t, "--body", body,
                        "--label", LABEL).strip()


def _check_repo(repo):
    if repo != REPO:
        raise ValueError(f"issues may only be opened in {REPO}, not {repo!r}")


def file_reports(reports, open_issues=False, client=None, out_dir="unknowns", repo=REPO):
    """Write every report to out_dir. If open_issues, open one issue per new fingerprint.
    Returns list of (fingerprint, action, url_or_path)."""
    _check_repo(repo)
    os.makedirs(out_dir, exist_ok=True)
    results = []
    existing = {}
    if open_issues:
        client = client or GhClient(repo)
        _check_repo(client.repo)
        client.ensure_label()
        for i in client.open_issue_bodies():
            for r in reports:
                if r["fingerprint"] in (i.get("body") or ""):
                    existing[r["fingerprint"]] = i["url"]
        # Local ledger covers the gap where a just-opened issue is not yet in the list API.
        ledger = _load_ledger(out_dir)
        for fp, url in ledger.items():
            if fp not in existing and any(r["fingerprint"] == fp for r in reports):
                body = client.issue_body_if_open(url)
                if body and fp in body:
                    existing[fp] = url
    seen_now = set()
    for r in reports:
        fp = r["fingerprint"]
        base = os.path.join(out_dir, fp)
        with open(base + ".json", "w") as f:
            json.dump(r, f, indent=2, default=str)
        with open(base + ".md", "w") as f:
            f.write(to_markdown(r))
        if fp in seen_now:
            continue
        seen_now.add(fp)
        if not open_issues:
            results.append((fp, "dry-run", base + ".md"))
        elif fp in existing:
            results.append((fp, "exists", existing[fp]))
        else:
            url = client.create_issue(title(r), to_markdown(r))
            existing[fp] = url
            _save_ledger(out_dir, fp, url)
            results.append((fp, "opened", url))
    return results


def _ledger_path(out_dir):
    return os.path.join(out_dir, "opened.json")


def _load_ledger(out_dir):
    try:
        with open(_ledger_path(out_dir)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_ledger(out_dir, fp, url):
    d = _load_ledger(out_dir); d[fp] = url
    with open(_ledger_path(out_dir), "w") as f:
        json.dump(d, f, indent=2)
