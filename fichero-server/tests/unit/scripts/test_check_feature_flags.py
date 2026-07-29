from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_feature_flags.py"
_SPEC = importlib.util.spec_from_file_location("check_feature_flags", _SCRIPT)
assert _SPEC and _SPEC.loader
check_feature_flags = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_feature_flags
_SPEC.loader.exec_module(check_feature_flags)  # type: ignore[attr-defined]


def test_no_new_on_by_default_feature_flags():
    """WIP flags must default off for release unless explicitly ratcheted."""
    found = check_feature_flags.scan()
    new = sorted(set(found) - set(check_feature_flags.KNOWN_VIOLATIONS))
    assert not new, (
        "New on-by-default feature flag(s). Default them off for release, or add a "
        "tracked KNOWN_VIOLATIONS entry naming the flag:\n  "
        + "\n  ".join(f"{key}  <-  {found[key]}" for key in new)
    )


def test_baseline_has_no_stale_signature_entries():
    """`main()` only warns on stale entries and still exits 0, so assert it here."""
    found = check_feature_flags.scan()
    stale = sorted(set(check_feature_flags.KNOWN_VIOLATIONS) - set(found))
    assert not stale, "Remove stale KNOWN_VIOLATIONS entries:\n  " + "\n  ".join(stale)


def test_main_fails_when_known_violations_are_stale(monkeypatch):
    monkeypatch.setattr(check_feature_flags, "scan", lambda: {})
    monkeypatch.setattr(
        check_feature_flags,
        "KNOWN_VIOLATIONS",
        {"FeatureManager.swift#deadbeef00": "test stale entry: fake_flag (declaration)"},
    )
    monkeypatch.setattr(sys, "argv", ["check_feature_flags.py"])

    assert check_feature_flags.main() == 1


def test_every_baseline_entry_names_the_flag_it_grandfathers():
    """Signatures are opaque hashes; the reason text is the only human-readable key.

    A value that does not name its own flag cannot be audited in review, and a
    copy-pasted entry would silently grandfather the wrong flag.
    """
    found = check_feature_flags.scan()
    mislabelled = []
    for key, reason in check_feature_flags.KNOWN_VIOLATIONS.items():
        if key not in found:
            continue  # stale entries are the other test's problem
        actual = found[key].split()[0].removeprefix("fichero.features.")
        # values read "<attribution>: <flag> (<site>)" -- compare the flag exactly, since
        # `search` is a prefix of `search_advanced_views` and a substring test would
        # happily accept the two swapped.
        claimed = reason.rpartition(": ")[2].partition(" (")[0]
        if claimed != actual:
            mislabelled.append(f"{key}: labelled {claimed!r}, but guards {actual!r}")
    assert not mislabelled, "KNOWN_VIOLATIONS entries must name their flag:\n  " + "\n  ".join(mislabelled)
