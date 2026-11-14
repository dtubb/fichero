"""2026-11-14 (owner: the builder hand-holds the lanes, not the manager): `builder precheck` runs the ladder's own guard rungs with the
pinned copies over a worktree's head; a stale allowlist entry is fixable by the lane (only-removed entries are judged by head's copy) and
its red carries the exact command; a missing Spec-change trailer and stale generated files carry theirs."""
from __future__ import annotations

import subprocess
import sys

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import autofix, check_tool, journal, queue, work

GUARD = '''import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
KNOWN_VIOLATIONS: dict[str, str] = {
    "a.swift": "kept",
    # why b is known
    "b.swift": (
        "a reason over two lines"
    ),
}
found = {p.name for p in ROOT.glob("*.swift")}
stale = sorted(set(KNOWN_VIOLATIONS) - found)
new = sorted(found - set(KNOWN_VIOLATIONS))
if stale:
    print(f"\\n  ✓ {len(stale)} KNOWN_VIOLATIONS entry now clean — drop from the set:")
    for k in stale:
        print(f"      {k}")
if new:
    print("new: " + ", ".join(new))
sys.exit(1 if stale or new else 0)
'''
SPEC_GUARD = '''import pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
log = subprocess.run(["git", "-C", str(ROOT), "log", "--format=%B", "origin/integration..HEAD"], capture_output=True, text=True).stdout
if (ROOT / "spec.md").read_text() != "acceptance\\n" and "Spec-change: " not in log:
    print("FAIL: spec.md: acceptance changed: restore it, or add a `Spec-change:` trailer naming the ruling")
    sys.exit(1)
'''
EMBED_GUARD = '''import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
if (ROOT / "embed.txt").read_text() != "".join(sorted(p.name + "\\n" for p in ROOT.glob("*.py"))):
    print("Engine embed filelist is STALE")
    sys.exit(1)
'''


def _g(cwd, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def world(tmp_path, monkeypatch):
    """origin (integration) with three guards; the pinned copy is a clone of it at the base; the lane is another clone."""
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    seed = tmp_path / "seed"
    (seed / "scripts").mkdir(parents=True)
    (seed / "scripts" / "check_known.py").write_text(GUARD)
    (seed / "scripts" / "check_spec_acceptance.py").write_text(SPEC_GUARD)
    (seed / "scripts" / "check_engine_embed_filelist.py").write_text(EMBED_GUARD)
    (seed / "a.swift").write_text(""), (seed / "b.swift").write_text(""), (seed / "spec.md").write_text("acceptance\n")
    (seed / "embed.txt").write_text("")
    (seed / "harness.toml").write_text(
        f'[check]\npython = "{sys.executable}"\nguard_glob = "scripts/check_*.py"\nmin_guards = 3\nbase_ref = "origin/integration"\n'
        'check_paths = ["scripts/", "harness.toml"]\nauto = ["allowlist-entries-only-removed"]\n'
        'regen = ["{python} scripts/regen_embed.py"]\nrebake_issue = "#4705"\n')
    _g(seed, "init", "-q", "-b", "integration"), _g(seed, "add", "."), _g(seed, "commit", "-qm", "base")
    _g(tmp_path, "clone", "-q", "--bare", str(seed), "origin.git")
    for d in ("pinned", "lane"):
        _g(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), d)
    return tmp_path


def _precheck(w):
    return queue.precheck(w, str(w / "lane"), "HEAD", str(w / "pinned"))


def test_allowlist_only_removed_is_entries_dropped_from_a_named_literal_and_nothing_else():
    base = 'KNOWN_VIOLATIONS = {"a": "x", "b": "y"}\nREQUIRED = {"r1", "r2"}\nLIMIT = 3\n'
    assert autofix.allowlist_only_removed("scripts/check_x.py", base, base.replace(', "b": "y"', ""))
    assert autofix.allowlist_only_removed("scripts/check_x.py", base, base.replace(', "b": "y"', "") + "# a comment is free\n")
    assert not autofix.allowlist_only_removed("scripts/check_x.py", base, base.replace(', "r2"', "")), "a REQUIRED set is not an allowlist"
    assert not autofix.allowlist_only_removed("scripts/check_x.py", base, base.replace('"b": "y"', '"c": "y"')), "an entry added"
    assert not autofix.allowlist_only_removed("scripts/check_x.py", base, base.replace(', "b": "y"', "").replace("3", "4")), "code changed too"
    assert not autofix.allowlist_only_removed("scripts/check_x.py", base, base), "no change is not a removal"
    gaps = '{"/a": "#1 a", "/b": "#2 b"}'
    assert autofix.allowlist_only_removed("scripts/x_known_gaps.json", gaps, '{"/a": "#1 a, reworded"}')
    assert not autofix.allowlist_only_removed("scripts/x_known_gaps.json", gaps, '{"/a": "#1 a", "/c": "#3"}')
    assert not autofix.allowlist_only_removed("scripts/routes.json", gaps, '{"/a": "#1 a"}'), "a JSON not named as an allowlist"


def test_precheck_runs_the_pinned_guards_over_the_head_and_a_stale_entry_red_carries_the_exact_one_line_fix(world, capsys):
    """2026-11-14: a batch deleted b.swift; the base guard said 'drop from the set' and the batch's own copy (or the pinned copy run from
    its own dir) said nothing. The precheck judges head with the pinned guard and prints the sed that drops exactly that entry; once the
    lane runs it, the edit (entries only removed) is judged with head's copy and is green, with one `auto` row."""
    lane = world / "lane"
    (lane / "scripts" / "check_known.py").write_text(GUARD.replace("sys.exit(1 if stale or new else 0)", "sys.exit(0)"))  # the lane's own copy hides it
    _g(lane, "rm", "-q", "b.swift"), _g(lane, "commit", "-qam", "drop b")
    rc, said = _precheck(world)
    assert rc == 1 and "FAIL: scripts/check_known.py" in said and "drop from the set" in said, "the PINNED guard judged head"
    (fix,) = [ln for ln in said.splitlines() if ln.startswith("Fix: scripts/check_known.py")]
    cmd = fix.split(": ", 3)[3].split(" (ruled")[0]
    assert cmd == "sed -i '' -e '6,8d' scripts/check_known.py", cmd
    _g(lane, "checkout", "-q", "HEAD~1", "--", "scripts/check_known.py")  # back to the base copy, then the lane runs the fix
    subprocess.run(cmd, shell=True, cwd=lane, check=True)
    assert '"b.swift"' not in (lane / "scripts" / "check_known.py").read_text() and '"a.swift"' in (lane / "scripts" / "check_known.py").read_text()
    _g(lane, "commit", "-qam", "drop the stale entry")
    rc, said = _precheck(world)
    assert rc == 0, said
    assert [r["file"] for r in journal.read() if r.get("rule") == "allowlist-entries-only-removed"][-1] == "scripts/check_known.py"
    assert len(_g(lane, "worktree", "list").splitlines()) == 1, "the scratch tree is gone"
    assert cli.main(["precheck", str(lane), "--pinned", str(world / "pinned"), "--state", str(journal.STATE)]) == 0
    assert "all green" in capsys.readouterr().out


def test_a_pinned_guard_edit_that_is_not_only_removed_entries_is_still_judged_by_the_pinned_copy(world):
    lane = world / "lane"
    _g(lane, "rm", "-q", "b.swift")
    (lane / "scripts" / "check_known.py").write_text(GUARD.replace('"b.swift"', '"c.swift"'))  # a swap: an entry added
    _g(lane, "commit", "-qam", "swap the entry")
    rc, said = _precheck(world)
    assert rc == 1 and "drop from the set" in said
    assert check_tool.stricter_files(lane, "origin/integration", "HEAD", check_tool.load(world / "pinned")) == ()


def test_a_missing_spec_change_trailer_and_a_stale_embed_list_each_carry_their_exact_command(world):
    lane = world / "lane"
    (lane / "spec.md").write_text("acceptance, rewritten\n")
    (lane / "new.py").write_text("")
    _g(lane, "add", "."), _g(lane, "commit", "-qm", "rewrite the acceptance, add a module")
    rc, said = _precheck(world)
    fixes = [ln for ln in said.splitlines() if ln.startswith("Fix: ")]
    assert rc == 1 and any("git commit --amend --no-edit --trailer \"Spec-change: " in f and "manager" in f for f in fixes), said
    assert any(f.startswith("Fix: scripts/check_engine_embed_filelist.py: regenerate and commit: .venv/bin/python scripts/regen_embed.py && git add -u")
               and "(#4705)" in f for f in fixes), said


def test_a_rebase_that_moved_the_lane_regenerates_the_generated_files_and_commits_them(tmp_path, monkeypatch):
    """2026-11-14: after a rebase the contracts and the embed list were stale and the guards bounced the batch. `[check].regen` runs in
    the worktree as the worker after a rebase that moved the lane, and a changed tracked file is one commit with the lane's trailers."""
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setattr(work, "as_worker", lambda a, script: subprocess.run(["sh", "-c", script], capture_output=True, text=True))
    for k, v in {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}.items():
        monkeypatch.setenv(k, v)
    e, w, pin = tmp_path / "engine", tmp_path / "wt", tmp_path / "pin"
    pin.mkdir()
    (pin / "harness.toml").write_text(f'[check]\npython = "{sys.executable}"\nrebake_issue = "#4705"\n'
                                      "regen = [\"{python} -c \\\"import pathlib; pathlib.Path('embed.txt').write_text(''.join(sorted(p.name + chr(10) for p in pathlib.Path('.').glob('*.py'))))\\\"\"]\n")
    e.mkdir()
    _g(e, "init", "-q", "-b", "integration"), (e / "embed.txt").write_text(""), _g(e, "add", "."), _g(e, "commit", "-qm", "base")
    _g(tmp_path, "clone", "-q", str(e), str(w))
    (w / "mine.py").write_text("")
    _g(w, "add", "."), _g(w, "commit", "-qm", "mine (#1)\n\nWritten-By: claude-opus-5-5")
    (e / "theirs.py").write_text("")
    _g(e, "add", "."), _g(e, "commit", "-qm", "theirs")  # no conflict: the list just goes stale under the rebase
    a = type("A", (), {"worktree": str(w), "name": "n1", "pinned": str(pin)})()
    assert work.do_rebase(a, "integration") == ""
    assert (w / "embed.txt").read_text() == "mine.py\ntheirs.py\n", "regenerated from the rebased tree"
    assert _g(w, "status", "--porcelain") == ""
    body = _g(w, "log", "-1", "--format=%B")
    assert body.startswith("chore(contract): regenerate the contracts and the engine embed list") and "(#4705)" in body and "Written-By: claude-opus-5-5" in body
    assert [r["detail"] for r in journal.read() if r["event"] == "rebake"][-1] == "regenerated after the rebase and committed"
    assert work.do_rebase(a, "integration") == "" and _g(w, "log", "-1", "--format=%s").startswith("chore(contract)"), "nothing moved: no second commit"


def test_an_entry_sharing_a_line_with_other_code_gets_no_sed_only_the_plain_ask():
    one_line = 'KNOWN_VIOLATIONS = {"a": "x", "b": "y"}\n'
    assert autofix.entry_lines(one_line, ["b"]) == {}
    hints = autofix.fix_hints("FAIL: scripts/check_x.py\n  drop from the set:\n      b\n", lambda f: one_line)
    assert hints == ["scripts/check_x.py: stale allowlist entries b: remove them from its allowlist (not found as one literal entry each)"]


def test_the_chains_red_alert_carries_the_fix_for_a_stale_entry_read_at_the_checked_head(world):
    """The loop's alert for an external lane (and a worker's fix brief) names the exact command, read from the head it judged."""
    lane = world / "lane"
    _g(lane, "rm", "-q", "b.swift"), _g(lane, "commit", "-qm", "drop b")
    head = _g(lane, "rev-parse", "HEAD")
    r = {"ok": False, "failed": "guards", "rungs": [{"name": "guards", "ok": False, "results": [
        {"name": "check_known", "ok": False, "stdout_tail": "  ✓ 1 KNOWN_VIOLATIONS entry now clean — drop from the set:\n      b.swift\n"}]}]}
    assert work.hints(r, str(lane), head, check_tool.load(world / "pinned")) == [
        "scripts/check_known.py: stale allowlist entries b.swift: sed -i '' -e '6,8d' scripts/check_known.py"
        " (ruled allowlist-entries-only-removed: the ladder judges with that copy)"]
