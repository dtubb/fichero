"""The issue/spec reconcile's pure decision logic (parse, classify, TSV round trip) is self-checking."""

import json

from fichero_builder import issue_reconcile


def _load():
    return issue_reconcile


def test_self_test_passes():
    assert _load().self_test() == 0


SPEC = """# S
> Milestone: m1

- `a.done` — **[BUILT]** (#1) pinned by `test_one`
- `a.half` — **[PARTIAL]** (#2) not all built, `test_two`
- `a.bug-done` — **[OK]** (#3) pinned by `test_three`
- `a.bug-notest` — **[OK]** (#4) works
"""

FAKE_GH = r"""#!/usr/bin/env python3
import json, sys, os
d = os.environ["FAKE_GH_DIR"]
a = sys.argv[1:]
open(d + "/calls", "a").write(" ".join(a) + "\n")
issues = json.load(open(d + "/issues.json"))
if a[:2] == ["issue", "view"]:
    n = a[2]
    if n not in issues:
        sys.exit(1)
    if "comments" in a:
        print("\n".join(issues[n].get("comments", [])))
    else:
        print(json.dumps({"state": issues[n]["state"], "labels": [{"name": x} for x in issues[n]["labels"]]}))
elif a[:2] == ["issue", "comment"]:
    issues[a[2]].setdefault("comments", []).append(sys.stdin.read())
    json.dump(issues, open(d + "/issues.json", "w"))
elif a[:2] == ["issue", "close"]:
    issues[a[2]]["state"] = "CLOSED"
    json.dump(issues, open(d + "/issues.json", "w"))
elif a[:2] == ["issue", "list"]:
    print(json.dumps([{"number": int(n), "labels": [{"name": x} for x in i["labels"]]}
                      for n, i in issues.items() if i["state"] == "OPEN"]))
"""


def _fake(tmp_path, monkeypatch, issues):
    mod = _load()
    gh = tmp_path / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    (tmp_path / "issues.json").write_text(json.dumps(issues))
    monkeypatch.setenv("FAKE_GH_DIR", str(tmp_path))
    monkeypatch.setattr(mod, "GH", str(gh))
    monkeypatch.setattr(mod, "load_specs", lambda ref: [("docs/s.md", SPEC)])
    monkeypatch.setattr(mod, "load_fixes", lambda ref: {4: ["fff111222"]})
    monkeypatch.setattr(mod, "test_missing_on_ref", lambda ref, names: set())
    return mod, lambda: json.loads((tmp_path / "issues.json").read_text())


def _issues(*spec):
    return {str(n): {"state": "OPEN", "labels": lb} for n, lb in spec}


def test_after_a_landing_done_issues_close_with_the_sha_bullets_and_tests_and_kept_ones_get_one_comment(tmp_path, monkeypatch):
    mod, state = _fake(tmp_path, monkeypatch, _issues((1, []), (2, []), (3, ["type:bug"]), (4, ["type:bug"]), (5, [])))
    out = {r["issue"]: r for r in mod.after_landing([1, 2, 3, 4, 5, 6], "HEAD", "abcdef123456789")}
    s = state()
    assert [out[n]["cls"] for n in (1, 2, 3, 4, 5)] == ["CLOSE-A", "KEEP", "CLOSE-A", "KEEP", "NO-SPEC"]
    assert out[6]["cls"] == "UNREAD", "an issue gh cannot read is said, never a traceback"
    assert s["1"]["state"] == "CLOSED" and s["3"]["state"] == "CLOSED"
    c = s["1"]["comments"][0]
    assert "abcdef123" in c and "a.done" in c and "`test_one`" in c
    assert s["2"]["state"] == "OPEN" and len(s["2"]["comments"]) == 1 and "a.half [PARTIAL]" in s["2"]["comments"][0]
    assert s["4"]["state"] == "OPEN" and "never closed without" in s["4"]["comments"][0], "a type:bug with no test is never closed (and a fix commit does not change that)"
    assert s["5"]["state"] == "OPEN"
    mod.after_landing([2], "HEAD", "abcdef123456789")
    assert len(state()["2"]["comments"]) == 1, "the same 'what is left' is not commented twice"


def test_an_already_closed_issue_is_left_alone(tmp_path, monkeypatch):
    mod, state = _fake(tmp_path, monkeypatch, {"1": {"state": "CLOSED", "labels": []}})
    assert mod.after_landing([1], "HEAD", "abc") == []
    assert "comments" not in state()["1"]


def test_nightly_writes_the_tsv_and_one_summary_and_closes_only_the_done(tmp_path, monkeypatch):
    mod, state = _fake(tmp_path, monkeypatch, _issues((1, []), (2, []), (4, ["type:bug"]), (7, [])))
    tsv = tmp_path / "out.tsv"
    summary = mod.nightly("HEAD", str(tsv))
    assert summary["open"] == 4 and summary["CLOSE-A"] == 1 and summary["KEEP"] == 2 and summary["NO-SPEC"] == 1 and summary["closed"] == 1
    assert [r.cls for r in mod.read_tsv(str(tsv))] == ["CLOSE-A", "KEEP", "KEEP", "NO-SPEC"]
    s = state()
    assert [s[n]["state"] for n in ("1", "2", "4", "7")] == ["CLOSED", "OPEN", "OPEN", "OPEN"]
    assert "comments" not in s["2"], "the nightly comments only on a close"


def test_only_the_cited_issues_tests_are_looked_up_and_in_one_git_grep(tmp_path, monkeypatch):
    mod, _ = _fake(tmp_path, monkeypatch, _issues((1, []), (3, ["type:bug"])))
    seen = []
    monkeypatch.setattr(mod, "test_missing_on_ref", lambda ref, names: (seen.append(set(names)), set())[1])
    mod.reconcile({1: False}, "HEAD")
    assert seen == [{"test_one"}], "the other bullets' tests are not read"
    calls = []
    monkeypatch.undo()
    monkeypatch.setattr(mod.subprocess, "run", lambda argv, **k: (calls.append(argv), mod.subprocess.CompletedProcess(argv, 1, "def test_n3\n", ""))[1])
    missing = mod.test_missing_on_ref("HEAD", {f"test_n{i}" for i in range(450)})
    assert len(calls) == 1 and "test_n3" not in missing and len(missing) == 449, "450 names: one grep, not 450"


def _git_in(cwd, *a):
    import subprocess
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *a], capture_output=True, text=True, check=True).stdout.strip()


def test_a_landing_whose_sha_is_only_on_the_remote_is_fetched_and_read(tmp_path, monkeypatch):
    """#6848: the reconcile ran `git ls-tree <sha>` in a clone without the landed sha and exited 128; it fetches first."""
    remote, other, clone = tmp_path / "remote.git", tmp_path / "other", tmp_path / "clone"
    _git_in(tmp_path, "init", "--bare", "-b", "main", str(remote))
    _git_in(tmp_path, "clone", "-q", str(remote), str(clone))
    (clone / "a.txt").write_text("1")
    _git_in(clone, "add", "."), _git_in(clone, "commit", "-qm", "one"), _git_in(clone, "push", "-q", "origin", "main")
    _git_in(tmp_path, "clone", "-q", str(remote), str(other))
    (other / "spec.md").write_text("2")
    _git_in(other, "add", "."), _git_in(other, "commit", "-qm", "landed"), _git_in(other, "push", "-q", "origin", "main")
    sha = _git_in(other, "rev-parse", "HEAD")
    monkeypatch.chdir(clone)
    mod = issue_reconcile
    import subprocess

    import pytest

    with pytest.raises(subprocess.CalledProcessError):
        mod._git("ls-tree", "-r", "--name-only", sha)  # the failure the audit saw
    mod.ensure_ref(sha)
    assert "spec.md" in mod._git("ls-tree", "-r", "--name-only", sha)


def test_after_landing_fetches_the_sha_before_it_reads_and_a_sha_nobody_has_is_said_per_issue(tmp_path, monkeypatch):
    mod, state = _fake(tmp_path, monkeypatch, _issues((1, []), (3, ["type:bug"])))
    seen = []
    monkeypatch.setattr(mod, "ensure_ref", lambda ref: seen.append(ref))
    assert mod.after_landing([1], "abc123", "abc123")[0]["cls"] == "CLOSE-A" and seen == ["abc123"]
    import subprocess

    def boom(ref):
        raise subprocess.CalledProcessError(128, ["git", "fetch"], "", "no such sha")
    monkeypatch.setattr(mod, "ensure_ref", boom)
    out = mod.after_landing([3], "abc123", "abc123")
    assert out[0]["issue"] == 3 and out[0]["cls"] == "UNREAD" and "reconcile failed" in out[0]["note"]
