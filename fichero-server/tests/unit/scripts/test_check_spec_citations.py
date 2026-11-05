"""scripts/check_spec_citations.py (dev-workflows.run.presubmit-lints, lints 3 and 4): the spec bullets a batch touches cite tests that
exist and say a current status; the whole tree's misses are a debt count that only falls. Offline: a scratch git repo."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_spec_citations.py"
_SPEC = importlib.util.spec_from_file_location("check_spec_citations", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

SPECS = "/".join(["docs", "contributor_manual", "specs"])  # built, so the spec-citation guards do not read it as a citation
OLD = "- `x.old` [PARTIAL] (#1) old text; test `tests/test_gone.py`.\n"


def _git(root, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(root), *a], check=True, capture_output=True, text=True).stdout


def _repo(tmp_path, debt):
    (tmp_path / SPECS).mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_real.py").write_text("def test_it_works():\n    assert True\n")
    (tmp_path / SPECS / "x.md").write_text(OLD)
    (tmp_path / SPECS / "_citation_debt.json").write_text(json.dumps(debt))
    _git(tmp_path, "init", "-q", "-b", "main"), _git(tmp_path, "add", "."), _git(tmp_path, "commit", "-qm", "base")
    _git(tmp_path, "update-ref", "refs/remotes/origin/integration", "HEAD")
    return tmp_path


def _touch(root, text):
    (root / SPECS / "x.md").write_text(OLD + text)
    _git(root, "add", "."), _git(root, "commit", "-qm", "batch")
    return _mod.check(root)[0]


def test_an_old_miss_in_an_untouched_bullet_is_debt_but_a_miss_in_a_touched_bullet_fails(tmp_path):
    root = _repo(tmp_path, {"missing_file": 1, "missing_name": 0})
    assert _mod.check(root)[0] == [], "the old bullet's missing file is counted in the debt, not failed"
    fails = _touch(root, "- `x.new` [PARTIAL] (#2) new; tests `tests/test_real.py::test_it_works`, `::test_not_there`, `tests/test_nope.py`.\n")
    rel = f"{SPECS}/x.md"
    assert f"{rel}:2: `tests/test_real.py::test_not_there` names nothing in that file" in fails
    assert f"{rel}:2: `tests/test_nope.py` does not exist" in fails
    assert not any(":1:" in f for f in fails), "the untouched bullet is not judged"


def test_a_stale_status_beside_an_existing_test_fails_and_an_ok_needs_a_test_but_a_not_built_note_is_fine(tmp_path):
    root = _repo(tmp_path, {"missing_file": 1, "missing_name": 0})
    fails = _touch(root, "- `x.gap` [GAP] (#2) gap; test `tests/test_real.py::test_it_works` (not yet written).\n"
                         "- `x.ok` [OK] (#3) done, no test cited.\n"
                         "- `x.part` [PARTIAL] (#4) **Not built:** the rest; test `tests/test_real.py::test_it_works`.\n"
                         "- `x.prose` [PARTIAL] (#5) a line tagged `[GAP]` or saying \"not yet written\" is stale; test `tests/test_real.py`.\n")
    assert any(":2: says '[GAP]' but its test `tests/test_real.py::test_it_works` exists" in f for f in fails), fails
    assert any(":3: tagged [OK] but cites no test file that exists" in f for f in fails)
    assert not any(":4:" in f for f in fails), "a 'Not built:' note beside an existing test is a fine status"
    assert not any(":5:" in f for f in fails), "a quoted or backticked status is prose about it, not a claim"


def test_the_debt_only_goes_down(tmp_path):
    root = _repo(tmp_path, {"missing_file": 0, "missing_name": 0})
    fails, _ = _mod.check(root)
    assert len(fails) == 1 and "allows 0: a citation broke outside this batch's bullets" in fails[0]
    (root / SPECS / "_citation_debt.json").write_text(json.dumps({"missing_file": 5, "missing_name": 0}))
    _git(root, "commit", "-qam", "raise it")
    fails, notes = _mod.check(root)
    assert any("was raised above its value at the base" in f for f in fails)
    assert any("lower it to 1" in n for n in notes), "fewer misses than the file says is a note, not a failure"


def test_a_missing_specs_dir_is_never_a_clean_read(tmp_path):
    with pytest.raises(FileNotFoundError):
        _mod.check(tmp_path)


def test_a_not_yet_elsewhere_naming_a_behaviour_the_batch_builds_fails_but_its_own_remaining_part_and_other_verbs_do_not(tmp_path):
    """Manager 2026-11-05 (review 105): batch-27 built `builder build-check` while another bullet of the same spec still said "Not yet:
    `builder build-check` from a lane". A batch's bullet names its id and the builder verb it opens with; a Not yet / Not built sentence
    naming either elsewhere in that spec fails. Its own bullet may still say what is left of it."""
    root = _repo(tmp_path, {"missing_file": 1, "missing_name": 0})
    stale = "- `x.incremental` [PARTIAL] (#1) builds in one tree. Not yet: `builder build-check` from a lane (the next batch).\n"
    other = "- `x.other` [PARTIAL] (#1) something. Not yet: `builder land --dry` and `x.unrelated`.\n"
    (root / SPECS / "x.md").write_text(OLD + stale + other)
    _git(root, "commit", "-qam", "base specs")
    _git(root, "update-ref", "refs/remotes/origin/integration", "HEAD")
    fails = _touch(root, stale + other + "- `x.check` [PARTIAL] (#2) — `builder build-check <lane>` compiles a lane; test "
                   "`tests/test_real.py::test_it_works`. Not built: a `builder build-check --watch` mode.\n")
    assert any(":2: says 'Not yet: `builder build-check` from a lane" in f and "line 4 builds" in f for f in fails), fails
    assert not any(":3:" in f for f in fails), "another verb and another id are not this batch's behaviour"
    assert not any(":4:" in f for f in fails), "the bullet's own Not built names what is left of it"
