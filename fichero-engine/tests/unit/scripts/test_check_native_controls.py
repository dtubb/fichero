from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_native_controls.py"
_SPEC = importlib.util.spec_from_file_location("check_native_controls", _SCRIPT)
assert _SPEC and _SPEC.loader
check_native_controls = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_native_controls
_SPEC.loader.exec_module(check_native_controls)  # type: ignore[attr-defined]


def test_no_new_hand_rolled_row_collections():
    """The backlog is frozen: the scan must find nothing outside KNOWN_VIOLATIONS."""
    found = check_native_controls.scan()
    new = sorted(set(found) - set(check_native_controls.KNOWN_VIOLATIONS))
    assert not new, "New hand-rolled row collection(s); use List/Table/OutlineGroup:\n  " + "\n  ".join(
        f"{key}  <-  {found[key]}" for key in new
    )


def test_baseline_has_no_stale_signature_entries():
    """`main()` only warns on stale entries and still exits 0, so assert it here.

    A stale entry is a signature the scan no longer produces: the violation was
    fixed, the file moved, or its snippet changed. Any of those should shrink
    the backlog rather than linger as a dead grandfather clause.
    """
    found = check_native_controls.scan()
    stale = sorted(set(check_native_controls.KNOWN_VIOLATIONS) - set(found))
    assert not stale, "Remove stale KNOWN_VIOLATIONS entries:\n  " + "\n  ".join(stale)
