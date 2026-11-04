"""Turn everything the robot doesn't know into 'unknown' reports, and (optionally) GitHub issues.

Issues are only ever opened in Almeidafly/button-bias. Default is dry-run: files in unknowns/.
Dedupe: fingerprint = kind + failed fields (not position, scene or time). Checked against
the committed ledger (unknowns/opened.json), all issues open AND closed, and GitHub search.
"""
import hashlib, json, os, subprocess
from dataclasses import fields as dc_fields
from datetime import datetime, timezone
from button_bias import Button, why_not_button, _kind

REPO = "Almeidafly/button-bias"
LABELS = ("unknown", "ejected")
DEFAULT_MAX_NEW = 5


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
    ref = Button("ref", (0, 0, 0), (1, 1), (0, 0, 1), (1, 2), (1, 2), "click", lambda a, b: True)
    out = []
    for n in names:
        probe = Button("probe", **{k: getattr(ref, k) for k in names})
        setattr(probe, n, getattr(obj, n))
        if why_not_button(probe) is not None:
            out.append(n)
    return out


def object_kind(obj):
    """Kind used for fingerprinting: declared kind/name, else the Python type. Never position."""
    k = _kind(obj) or str(getattr(obj, "name", "") or "").strip().lower()
    return f"{type(obj).__name__}:{k}"


def fingerprint(kind, failed):
    raw = json.dumps([kind, sorted(failed)])
    return "bb2-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def report_ejected(obj, record, scene, now=None):
    kind, failed = object_kind(obj), bad_fields(obj)
    return {"fingerprint": fingerprint(kind, failed), "kind": "ejected", "object_kind": kind,
            "name": record["name"], "reason": why_not_button(obj), "bad_fields": failed,
            "ejected": {k: v for k, v in record.items() if k != "object"},
            "seen": _describe(obj), "scene": scene,
            "timestamp": (now or datetime.now(timezone.utc)).isoformat()}


def report_dark(button, before, after, scene, cause="unexplained", now=None):
    kind = f"dark-press:{button.name}"
    return {"fingerprint": fingerprint(kind, [cause]), "kind": "dark-press", "object_kind": kind,
            "name": button.name, "reason": f"dark press, cause: {cause}", "bad_fields": [],
            "seen": {"before": before, "after_press": after}, "scene": scene,
            "timestamp": (now or datetime.now(timezone.utc)).isoformat()}


def to_markdown(r):
    ej = r.get("ejected")
    ej_txt = (f"- **ejected:** from scene slot {ej['from_index']} (position {ej['from_position']}) "
              f"into eject bin slot {ej['bin_slot']}. Never pressed.\n") if ej else ""
    return (f"The robot does not know this thing, so it ejected it.\n\n- **kind:** {r['object_kind']}\n"
            f"- **name:** `{r['name']}`\n- **reason:** {r['reason']}\n"
            f"- **missing/invalid Button fields:** {', '.join(r['bad_fields']) or 'none'}\n{ej_txt}"
            f"- **scene:** {r['scene']}\n- **first seen:** {r['timestamp']}\n\n"
            f"What it saw:\n```json\n{json.dumps(r['seen'], indent=2, default=str)}\n```\n\n"
            f"fingerprint: `{r['fingerprint']}`\n\n_Simulation only. Opened by button-bias._\n")


def title(r):
    return f"[unknown] {r['kind']}: {r['name'][:60]} (fails: {', '.join(r['bad_fields']) or r['reason'][:40]})"


def _check_repo(repo):
    if repo != REPO:
        raise ValueError(f"issues may only be opened in {REPO}, not {repo!r}")


class GhClient:
    """Real client using the gh CLI. Locked to REPO. Never edits or comments on issues."""
    def __init__(self, repo=REPO):
        _check_repo(repo); self.repo = repo

    def _gh(self, *args):
        return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout

    def ensure_labels(self):
        for name in LABELS:
            subprocess.run(["gh", "label", "create", name, "--repo", self.repo, "--color", "888888"],
                           capture_output=True)

    def all_issues(self):
        """Open AND closed issues: [{number, state, body, url}]."""
        return json.loads(self._gh("issue", "list", "--repo", self.repo, "--state", "all",
                                   "--limit", "1000", "--json", "number,state,body,url"))

    def get_issue(self, url):
        try:
            return json.loads(self._gh("issue", "view", url, "--repo", self.repo,
                                       "--json", "number,state,body,url"))
        except subprocess.CalledProcessError:
            return None

    def search(self, fp):
        try:
            return json.loads(self._gh("search", "issues", fp, "--repo", self.repo, "--include-prs=false",
                                       "--json", "number,state,body,url"))
        except subprocess.CalledProcessError:
            return []

    def create_issue(self, t, body):
        args = ["issue", "create", "--repo", self.repo, "--title", t, "--body", body]
        for name in LABELS:
            args += ["--label", name]
        return self._gh(*args).strip()


def _ledger_path(out_dir):
    return os.path.join(out_dir, "opened.json")


def load_ledger(out_dir):
    try:
        with open(_ledger_path(out_dir)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_ledger(out_dir, fp, url):
    d = load_ledger(out_dir); d[fp] = url
    with open(_ledger_path(out_dir), "w") as f:
        json.dump(d, f, indent=2, sort_keys=True)
        f.write("\n")


def _find_existing(client, fp, ledger, cache):
    """Return an issue dict {number, state, url} carrying fp, or None. Ledger -> list -> search."""
    if fp in ledger:
        i = client.get_issue(ledger[fp])
        if i and fp in (i.get("body") or ""):
            return i
    for i in cache:
        if fp in (i.get("body") or ""):
            return i
    for i in client.search(fp):
        if fp in (i.get("body") or ""):
            return i
    return None


def file_reports(reports, open_issues=False, client=None, out_dir="unknowns", repo=REPO,
                 max_new=DEFAULT_MAX_NEW):
    """Write every report to out_dir. If open_issues, open at most max_new issues for new
    fingerprints; anything over the cap stays a dry-run file. Returns [(fp, action, where)]."""
    _check_repo(repo)
    os.makedirs(out_dir, exist_ok=True)
    if open_issues:
        client = client or GhClient(repo)
        _check_repo(client.repo)
        client.ensure_labels()
        cache = client.all_issues()
        ledger = load_ledger(out_dir)
    results, done, opened = [], set(), 0
    for r in reports:
        fp = r["fingerprint"]
        base = os.path.join(out_dir, fp)
        with open(base + ".json", "w") as f:
            json.dump(r, f, indent=2, default=str)
        with open(base + ".md", "w") as f:
            f.write(to_markdown(r))
        if fp in done:
            continue
        done.add(fp)
        if not open_issues:
            results.append((fp, "dry-run", base + ".md")); continue
        hit = _find_existing(client, fp, ledger, cache)
        if hit:
            if fp not in ledger:
                _save_ledger(out_dir, fp, hit["url"]); ledger[fp] = hit["url"]
            if str(hit.get("state", "")).upper() == "CLOSED":
                results.append((fp, "seen-before", f"seen before (closed #{hit.get('number')})"))
            else:
                results.append((fp, "exists", hit["url"]))
            continue
        if opened >= max_new:
            results.append((fp, "capped", base + ".md")); continue
        url = client.create_issue(title(r), to_markdown(r))
        opened += 1
        _save_ledger(out_dir, fp, url); ledger[fp] = url
        cache.append({"url": url, "state": "OPEN", "body": to_markdown(r)})
        results.append((fp, "opened", url))
    return results
