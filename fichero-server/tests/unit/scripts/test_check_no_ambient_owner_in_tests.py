"""Unit tests for scripts/check_no_ambient_owner_in_tests.py (multiuser.ambient-owner-leaves-the-tests).

The ratchet is 44: 43 unnamed offenders plus one named exception (the shipped embedded Set Up walk). A 45th, or an
unnamed offender that takes the named walk's place, must fail.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_no_ambient_owner_in_tests.py"
_SPEC = importlib.util.spec_from_file_location("check_no_ambient_owner_in_tests", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

NAMED_ID = next(iter(_mod.NAMED))
STORED = 44
OWNER_CALL = "." + "host" + "()"  # spelled apart so this file is not itself an offender


def _tree(tmp_path: Path, others: int, named_body: str = f"    app = harness{OWNER_CALL}\n") -> Path:
    named_file = tmp_path / NAMED_ID.split("::")[0]
    named_file.parent.mkdir(parents=True)
    named_file.write_text(f"def {NAMED_ID.split('::')[1]}(harness):\n{named_body}\n\ndef test_other():\n    pass\n")
    for i in range(others):
        (named_file.parent / f"test_x{i}.py").write_text(f"def test_x(harness):\n    harness{OWNER_CALL}\n")
    return tmp_path


def _verdict(root: Path) -> str | None:
    return _mod.verdict(*_mod.scan(root), STORED)


def test_43_unnamed_plus_the_named_walk_passes(tmp_path):
    assert _verdict(_tree(tmp_path, 43)) is None


def test_an_unnamed_44th_fails(tmp_path):
    assert "unnamed" in (_verdict(_tree(tmp_path, 44)) or "")


def test_an_unnamed_offender_cannot_take_the_place_of_the_named_walk(tmp_path):
    # Same total (44), but the named test is gone and an unnamed one stands in for it.
    root = _tree(tmp_path, 43, named_body="    pass\n")
    (root / NAMED_ID.split("::")[0]).parent.joinpath("test_extra.py").write_text(f"def test_y(h):\n    h{OWNER_CALL}\n")
    assert _verdict(root)


def test_a_vanished_named_test_must_be_dropped_from_the_allowlist(tmp_path):
    root = tmp_path
    (root / "fichero-server" / "tests").mkdir(parents=True)
    assert "no longer exists" in (_verdict(root) or "")


def test_the_real_tree_is_at_the_baseline():
    total, unnamed, missing = _mod.scan()
    assert not missing and total == STORED and unnamed == STORED - len(_mod.NAMED)
