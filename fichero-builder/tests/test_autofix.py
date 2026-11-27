"""2026-11-14 (owner: the builder hand-holds the lanes, not the manager): `builder precheck` runs the ladder's own guard rungs with the
pinned copies over a worktree's head; a stale allowlist entry is fixable by the lane (only-removed entries are judged by head's copy) and
its red carries the exact command; a missing Spec-change trailer and stale generated files carry theirs."""
from __future__ import annotations

import re
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


def _delete_lines(path, sed_cmd):
    """Apply the printed `sed -i '' -e 'A,Bd' FILE` fix as the lane's Mac would, without sed: GNU sed reads `-i ''` as a file name."""
    m = re.fullmatch(r"sed -i '' -e '(\d+),(\d+)d' (\S+)", sed_cmd)
    assert m and path.name == m[3].rsplit("/", 1)[-1], sed_cmd
    lines = path.read_text().splitlines(keepends=True)
    path.write_text("".join(lines[: int(m[1]) - 1] + lines[int(m[2]):]))


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
    assert autofix.allowlist_only_removed("scripts/x_known_gaps.json", gaps, '{"/a": "#1 a"}')
    assert not autofix.allowlist_only_removed("scripts/x_known_gaps.json", gaps, '{"/a": "#1 a", "/c": "#3"}')
    assert not autofix.allowlist_only_removed("scripts/routes.json", gaps, '{"/a": "#1 a"}'), "a JSON not named as an allowlist"


def test_precheck_runs_the_pinned_guards_over_the_head_and_a_stale_entry_red_carries_the_exact_one_line_fix(world, capsys):
    """2026-11-14: a batch deleted b.swift; the base guard said 'drop from the set' and the batch's own copy (or the pinned copy run from
    its own dir) said nothing. The precheck judges head with the pinned guard and prints the sed that drops exactly that entry; once the
    lane runs it, the edit (the pinned copy minus entries) is judged with head's copy and is green."""
    lane = world / "lane"
    (lane / "scripts" / "check_known.py").write_text(GUARD.replace("sys.exit(1 if stale or new else 0)", "sys.exit(0)"))  # the lane's own copy hides it
    _g(lane, "rm", "-q", "b.swift"), _g(lane, "commit", "-qam", "drop b")
    rc, said = _precheck(world)
    assert rc == 1 and "FAIL: scripts/check_known.py" in said and "drop from the set" in said, "the PINNED guard judged head"
    (fix,) = [ln for ln in said.splitlines() if ln.startswith("Fix: scripts/check_known.py")]
    cmd = fix.split(": ", 3)[3].split(" (ruled")[0]
    assert cmd == "sed -i '' -e '6,8d' scripts/check_known.py", cmd
    _g(lane, "checkout", "-q", "HEAD~1", "--", "scripts/check_known.py")  # back to the base copy, then the lane runs the fix
    _delete_lines(lane / "scripts" / "check_known.py", cmd)  # what the printed sed does, in Python: `sed -i ''` is BSD-only (ci.python-tiers)
    assert '"b.swift"' not in (lane / "scripts" / "check_known.py").read_text() and '"a.swift"' in (lane / "scripts" / "check_known.py").read_text()
    _g(lane, "commit", "-qam", "drop the stale entry")
    rc, said = _precheck(world)
    assert rc == 0, said
    assert check_tool.stricter_files(lane, "origin/integration", "HEAD", check_tool.load(world / "pinned"), world / "pinned") == ("scripts/check_known.py",)
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
    assert check_tool.stricter_files(lane, "origin/integration", "HEAD", check_tool.load(world / "pinned"), world / "pinned") == ()


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


def test_a_ratchet_baseline_json_or_a_reworded_entry_is_never_only_removed():
    """Review of 916d5422d4: a key removed from scripts/release_size_baseline.json read as 'only removed', and the ratchet then treated
    it as a first run (looser). Only known-gaps and allowlist files qualify, and every kept entry must be identical."""
    sizes = '{"app": 10, "engine": 20}'
    assert not autofix.allowlist_only_removed("scripts/release_size_baseline.json", sizes, '{"app": 10}')
    assert not autofix.allowlist_only_removed("scripts/check_x.py", 'BASELINE = {"a": 1, "b": 2}\n', 'BASELINE = {"a": 1}\n')
    gaps = '{"/a": "#1 a", "/b": "#2 b"}'
    assert not autofix.allowlist_only_removed("scripts/x_known_gaps.json", gaps, '{"/a": "#1 reworded"}')


def test_a_lane_copy_of_a_guard_older_than_the_pinned_one_never_replaces_it(world):
    """Review of 916d5422d4: 'only removed' was judged against the lane's merge base, so a guard integration changed after the lane
    branched was replaced by the lane's older copy minus an entry. It is judged against the PINNED copy; only the ladder writes the row."""
    lane, pinned = world / "lane", world / "pinned"
    _g(lane, "rm", "-q", "b.swift")
    lines = (lane / "scripts" / "check_known.py").read_text().splitlines(keepends=True)
    (lane / "scripts" / "check_known.py").write_text("".join(lines[:5] + lines[8:]))  # the b.swift entry's three lines
    _g(lane, "commit", "-qam", "drop b and its entry")
    cfg = check_tool.load(pinned)
    assert check_tool.stricter_files(lane, "origin/integration", "HEAD", cfg, pinned) == ("scripts/check_known.py",)
    guard = pinned / "scripts" / "check_known.py"
    guard.write_text(guard.read_text().replace("sys.exit(1 if stale or new else 0)", "sys.exit(1 if stale or new or len(found) > 5 else 0)"))
    assert check_tool.stricter_files(lane, "origin/integration", "HEAD", cfg, pinned) == (), "integration's newer guard is never replaced"
    assert not [r for r in journal.read() if r.get("rule") == "allowlist-entries-only-removed"]


def test_regen_without_a_python_is_refused_in_the_rules(tmp_path):
    (tmp_path / "harness.toml").write_text('[check]\nregen = ["{python} x.py"]\n')
    with pytest.raises(ValueError, match="regen needs"):
        check_tool.load(tmp_path)


# local.autofix.loop-applies-the-printed-fix / local.autofix.classes (#6589)
KNOWN_RED = "FAIL: scripts/check_endpoint_coverage_matrix.py\n  2 KNOWN_GAPS entries are now clean; remove them:\n      GET /a\n      GET /c\n"
REAL_KNOWN_RED = (
    "FAIL: scripts/check_endpoint_coverage_matrix.py\n"
    "Endpoint coverage matrix guardrail:\n  scanned 664 operation(s)\n  current gaps: 3; known baseline: 3\n"
    "\n  2 KNOWN_GAPS entries are now clean; remove them:\n      GET /a\n      GET /c\n"
    "  operations no spec names: 4; baseline: 5\n"
    "\n  1 route(s) no spec names (add a behaviour line naming the path or operation id, with its app plan):\n      GET /z\n")
RATCHET_RED = "FAIL: scripts/check_ratchet.py\nFAIL: down to 3 (baseline 5): lower it with --update-baseline.\n"
SPEC_RED = "FAIL: scripts/check_spec_acceptance.py\nFAIL: spec.md: acceptance changed: add a `Spec-change:` trailer\n"
RULING = "Spec-change: the acceptance line was reworded, ruled by the manager 2026-11-24"


@pytest.fixture
def lane_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setattr(work, "as_worker", lambda a, script: subprocess.run(["sh", "-c", script], capture_output=True, text=True))
    for k, v in {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}.items():
        monkeypatch.setenv(k, v)
    pin, w = tmp_path / "pin", tmp_path / "wt"
    (w / "scripts").mkdir(parents=True), pin.mkdir()
    (pin / "harness.toml").write_text(f'[check]\npython = "{sys.executable}"\nautofix = ["known-gaps-now-clean", "ratchet-baseline-lower", "spec-change-trailer"]\n')
    (w / "scripts" / "check_endpoint_coverage_matrix_known_gaps.json").write_text('{\n  "GET /a": "x",\n  "GET /b": "y",\n  "GET /c": "z"\n}\n')
    (w / "scripts" / "check_ratchet.py").write_text("import sys\nprint('ok')\nif '--update-baseline' in sys.argv:\n    open('scripts/ratchet.json', 'w').write('{\"n\": 3}\\n')\n")
    (w / "scripts" / "ratchet.json").write_text('{"n": 5}\n')
    (w / "other.txt").write_text("keep\n")
    _g(w, "init", "-q", "-b", "integration"), _g(w, "add", "."), _g(w, "commit", "-qm", "mine (#1)\n\nWritten-By: claude-opus-5-5")
    return type("A", (), {"worktree": str(w), "name": "n1", "pinned": str(pin)})(), w, pin


def test_the_guards_real_output_with_lines_after_the_key_block_drops_only_the_stale_keys(lane_repo):
    a, w, _ = lane_repo
    assert autofix.stale_keys(REAL_KNOWN_RED, whole=True) == ["GET /a", "GET /c"]
    before = _g(w, "rev-parse", "HEAD")
    res = work.autofix(a, "1.1", REAL_KNOWN_RED, "")
    assert [r["class"] for r in res["rows"]] == ["known-gaps-now-clean"] and _g(w, "rev-parse", "HEAD") != before
    assert (w / "scripts" / "check_endpoint_coverage_matrix_known_gaps.json").read_text() == '{\n  "GET /b": "y"\n}\n'


def test_a_known_gaps_red_is_one_commit_with_the_lane_trailers_one_autofix_row_and_only_the_named_entries_gone(lane_repo):
    a, w, _ = lane_repo
    before = _g(w, "rev-parse", "HEAD")
    res = work.autofix(a, "1.1", KNOWN_RED, "")
    assert (w / "scripts" / "check_endpoint_coverage_matrix_known_gaps.json").read_text() == '{\n  "GET /b": "y"\n}\n'
    assert _g(w, "rev-list", "--count", f"{before}..HEAD") == "1" and _g(w, "status", "--porcelain") == ""
    assert "Written-By: claude-opus-5-5" in _g(w, "log", "-1", "--format=%B")
    row = [r for r in journal.read() if r["event"] == "autofix"]
    assert len(row) == 1 and (row[0]["class"], row[0]["before"], row[0]["after"], row[0]["files"]) == (
        "known-gaps-now-clean", before, _g(w, "rev-parse", "HEAD"), ["scripts/check_endpoint_coverage_matrix_known_gaps.json"])
    assert res["rows"][0]["class"] == "known-gaps-now-clean" and not res["ask"]


def test_a_ratchet_that_prints_a_lower_count_is_lowered_and_one_that_would_rise_is_left(lane_repo):
    a, w, _ = lane_repo
    assert work.autofix(a, "1.1", RATCHET_RED.replace("down to 3 (baseline 5)", "down to 7 (baseline 5)"), "") == {"rows": [], "ask": False}
    assert (w / "scripts" / "ratchet.json").read_text() == '{"n": 5}\n'
    assert work.autofix(a, "1.1", RATCHET_RED, "")["rows"][0]["files"] == ["scripts/ratchet.json"]
    assert (w / "scripts" / "ratchet.json").read_text() == '{"n": 3}\n'


def test_a_fix_that_changes_a_file_outside_its_class_is_undone_and_changes_nothing(lane_repo):
    a, w, _ = lane_repo
    (w / "scripts" / "check_ratchet.py").write_text("open('other.txt', 'w').write('changed')\n")
    _g(w, "commit", "-qam", "rewrite")
    head = _g(w, "rev-parse", "HEAD")
    assert work.autofix(a, "1.1", RATCHET_RED, "")["rows"] == []
    assert (w / "other.txt").read_text() == "keep\n" and _g(w, "rev-parse", "HEAD") == head and _g(w, "status", "--porcelain") == ""


def test_a_spec_change_red_gets_the_briefs_line_word_for_word_and_none_without_one_is_a_question(lane_repo):
    a, w, _ = lane_repo
    assert work.autofix(a, "1.1", SPEC_RED, "do it\n") == {"rows": [], "ask": True}, "no ruling in the brief: the manager is asked"
    assert "Spec-change" not in _g(w, "log", "-1", "--format=%B")
    res = work.autofix(a, "1.1", SPEC_RED, f"do it\n{RULING}\n")
    assert _g(w, "log", "-1", "--format=%B").splitlines()[-2:] == [RULING, "Written-By: claude-opus-5-5"] and res["rows"][0]["files"] == []
    assert _g(w, "rev-list", "--count", "HEAD") == "1", "the trailer amends the lane's head: no new commit"


def test_a_class_not_named_in_the_rules_is_never_tried_and_an_unknown_class_refuses_the_rules_file(lane_repo, tmp_path):
    a, w, pin = lane_repo
    (pin / "harness.toml").write_text(f'[check]\npython = "{sys.executable}"\nautofix = ["spec-change-trailer"]\n')
    assert work.autofix(a, "1.1", KNOWN_RED, "") == {"rows": [], "ask": False}
    assert work.autofix(a, "1.1", KNOWN_RED, "", skip=("spec-change-trailer",)) == {"rows": [], "ask": False}
    (tmp_path / "harness.toml").write_text('[check]\nautofix = ["rm-rf"]\n')
    with pytest.raises(ValueError, match="unknown autofix classes"):
        check_tool.load(tmp_path)


def test_an_openapi_regen_red_runs_the_regen_lines_and_commits_the_tracked_files_they_changed(lane_repo):
    a, w, pin = lane_repo
    (pin / "harness.toml").write_text(f'[check]\npython = "{sys.executable}"\nautofix = ["openapi-regen"]\n'
                                      "regen = [\"{python} -c \\\"open('other.txt', 'w').write('regenerated')\\\"\"]\n")
    res = work.autofix(a, "1.1", "FAIL: scripts/check_openapi_contract.py\ngenerated copy is stale\n", "")
    assert res["rows"][0]["files"] == ["other.txt"] and (w / "other.txt").read_text() == "regenerated"
    assert work.autofix(a, "1.1", "FAIL: scripts/check_other.py\nall fine\n", "")["rows"] == []


def test_a_fix_commit_carries_only_the_heads_written_by_line_and_a_head_without_one_is_left_to_the_worker(lane_repo):
    a, w, _ = lane_repo
    _g(w, "commit", "--amend", "-qm", "mine (#1)\n\nDirected-By: x\nWritten-By: claude-opus-5-5\nCo-Authored-By: y")
    work.autofix(a, "1.1", KNOWN_RED, "")
    assert _g(w, "log", "-1", "--format=%B").split("\n\n", 1)[1].strip() == "Written-By: claude-opus-5-5"
    _g(w, "commit", "--amend", "-qm", "no trailer (#1)")
    before = _g(w, "rev-parse", "HEAD")
    assert work.autofix(a, "1.1", RATCHET_RED, "")["rows"] == [] and _g(w, "rev-parse", "HEAD") == before and _g(w, "status", "--porcelain") == ""


def test_a_file_a_failed_fix_created_is_removed_and_the_workers_own_untracked_file_stays(lane_repo):
    a, w, _ = lane_repo
    (w / "scripts" / "check_ratchet.py").write_text("open('stray.txt', 'w').write('x')\nopen('scripts/ratchet.json', 'w').write('{}')\n")
    _g(w, "commit", "-qam", "rewrite")
    (w / "mine.txt").write_text("worker's")
    assert work.autofix(a, "1.1", RATCHET_RED, "")["rows"] == []
    assert not (w / "stray.txt").exists() and (w / "mine.txt").read_text() == "worker's"


def test_uncommitted_tracked_edits_survive_every_class_and_the_red_goes_to_the_worker(lane_repo):
    a, w, _ = lane_repo
    (w / "other.txt").write_text("worker's edit\n")
    (w / "scripts" / "ratchet.json").write_text('{"n": 9}\n')
    _g(w, "add", "scripts/ratchet.json")
    head = _g(w, "rev-parse", "HEAD")
    for red, brief in ((KNOWN_RED, ""), (RATCHET_RED, ""), (SPEC_RED, f"do it\n{RULING}\n")):
        assert work.autofix(a, "1.1", red, brief) == {"rows": [], "ask": False}
    assert _g(w, "rev-parse", "HEAD") == head and "Spec-change" not in _g(w, "log", "-1", "--format=%B")
    assert (w / "other.txt").read_text() == "worker's edit\n" and (w / "scripts" / "ratchet.json").read_text() == '{"n": 9}\n'
    assert _g(w, "status", "--porcelain").splitlines() == ["M other.txt", "M  scripts/ratchet.json"]
