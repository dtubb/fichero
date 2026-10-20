"""Unit tests for scripts/check_no_ambient_owner_in_tests.py (multiuser.ambient-owner-leaves-the-tests).

The ratchet is the stored baseline: the named exceptions plus the unnamed offenders it allows. One more unnamed
offender, or an unnamed offender that takes a named test's place, must fail.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_no_ambient_owner_in_tests.py"
_SPEC = importlib.util.spec_from_file_location("check_no_ambient_owner_in_tests", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

NAMED_ID = next(iter(_mod.NAMED))
STORED = json.loads((_SCRIPT.parent / "ambient_owner_in_tests_baseline.json").read_text())["count"]
UNNAMED = STORED - _mod._ALLOWED  # the unnamed offenders the baseline allows
OWNER_CALL = "." + "host" + "()"  # spelled apart so this file is not itself an offender


def _tree(tmp_path: Path, others: int, named_body: str = f"    app = harness{OWNER_CALL}\n") -> Path:
    named_file = tmp_path / NAMED_ID.split("::")[0]
    named_file.parent.mkdir(parents=True)
    named_file.write_text(f"def {NAMED_ID.split('::')[1]}(harness):\n{named_body}\n\ndef test_other():\n    pass\n")
    for test_id in list(_mod.NAMED)[1:]:  # every other named test, at its one allowed line
        other = tmp_path / test_id.split("::")[0]
        other.parent.mkdir(parents=True, exist_ok=True)
        with other.open("a") as f:
            f.write(f"\ndef {test_id.split('::')[1]}(harness):\n    app = harness{OWNER_CALL}\n")
    for i in range(others):
        (named_file.parent / f"test_x{i}.py").write_text(f"def test_x(harness):\n    harness{OWNER_CALL}\n")
    return tmp_path


def _verdict(root: Path) -> str | None:
    return _mod.verdict(*_mod.scan(root), STORED)


def test_the_allowed_unnamed_plus_the_named_tests_pass(tmp_path):
    assert _verdict(_tree(tmp_path, UNNAMED)) is None


def test_one_more_unnamed_fails(tmp_path):
    assert "unnamed" in (_verdict(_tree(tmp_path, UNNAMED + 1)) or "")


def test_an_unnamed_offender_cannot_take_the_place_of_the_named_walk(tmp_path):
    # Same total, but the named test's line is gone and an unnamed one stands in for it.
    root = _tree(tmp_path, UNNAMED, named_body="    pass\n")
    (root / NAMED_ID.split("::")[0]).parent.joinpath("test_extra.py").write_text(f"def test_y(h):\n    h{OWNER_CALL}\n")
    assert _verdict(root)


def test_a_vanished_named_test_must_be_dropped_from_the_allowlist(tmp_path):
    root = tmp_path
    (root / "fichero-server" / "tests").mkdir(parents=True)
    assert "no longer exists" in (_verdict(root) or "")


def test_the_real_tree_is_at_the_baseline():
    total, unnamed, missing, over = _mod.scan()
    assert not missing and not over and total == STORED and unnamed == STORED - _mod._ALLOWED


def test_a_named_test_cannot_grow_past_its_allowed_lines(tmp_path):
    # One unnamed slot is free, the named walk gains a second line: the total stays at the baseline but the walk is over.
    body = f"    app = harness{OWNER_CALL}\n    other = harness{OWNER_CALL}\n"
    assert "more lines" in (_verdict(_tree(tmp_path, UNNAMED - 1, named_body=body)) or "")


HANDLE = "Bearer " + "{self" + ".token}"  # spelled apart so this file is not itself an offender


def test_a_bootstrap_token_held_in_an_engine_handle_is_caught(tmp_path):
    """The two-engine harness minted with an f-string over its engine handle that the first pattern missed (## 582)."""
    root = _tree(tmp_path, 0)
    (root / "fichero-server" / "tests" / "test_handle.py").write_text(f'def test_h(self):\n    h = f"{HANDLE}"\n')
    assert _mod.scan(root)[1] == 1
