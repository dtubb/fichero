"""Baseline hygiene for the canonical-renderer guardrail (#4174 audit).

This was the ONE guardrail of 46 whose baseline could only grow: it reported
"known" vs "new" but never surfaced entries that had stopped matching. That is
worse here than in the other guardrails because `KNOWN_EXTENSIONS` matches by
SUBSTRING — a dead entry is not inert, it is a standing wildcard that exempts
any future symbol whose name happens to contain the fragment.

The audit found exactly one such entry, dead since it was written: its fragment
was `row(for claim`, and a "(" cannot appear in a captured Swift identifier.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "check_canonical_renderers.py"


def _load():
    spec = importlib.util.spec_from_file_location("_canonical_renderers", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load()


def test_baseline_has_no_entries_that_match_nothing():
    """The enforcement test: a dead exemption is an expanding hole."""
    matches = guard.entry_matches()
    stale = [
        f"{guard.KNOWN_EXTENSIONS[i][0]} :: {guard.KNOWN_EXTENSIONS[i][1]}"
        for i, hits in enumerate(matches)
        if not hits
    ]

    assert not stale, (
        "KNOWN_EXTENSIONS entries matching nothing (remove them — substring "
        "matching makes them wildcards, not dead weight):\n  " + "\n  ".join(stale)
    )


def test_every_entry_is_reported_with_its_matches():
    """Sanity: the accounting lines up with what the scan actually found."""
    matches = guard.entry_matches()
    findings = guard.scan()

    assert len(matches) == len(guard.KNOWN_EXTENSIONS)
    assert sum(len(hits) for hits in matches) == len([f for f in findings if f["known"]])


def test_stale_entry_is_detected(monkeypatch):
    """Proves the detection FIRES — a check that can only report zero is inert.

    Learned the hard way on #4201: a rule reporting 0 findings is
    indistinguishable from a broken rule without a positive fixture.
    """
    monkeypatch.setattr(
        guard,
        "KNOWN_EXTENSIONS",
        [("no-such-file.swift", "noSuchSymbol", "deliberately unmatched")],
    )

    matches = guard.entry_matches()

    assert matches == [[]], "a fabricated entry must be reported as matching nothing"


def test_live_entry_is_not_reported_as_stale(monkeypatch):
    """The negative: a real exemption must NOT be flagged, or the fix is useless."""
    real_findings = [f for f in guard.scan() if f["known"]]
    assert real_findings, "expected the repo to contain at least one known extension"
    sample = real_findings[0]

    monkeypatch.setattr(
        guard,
        "KNOWN_EXTENSIONS",
        [(sample["file"], sample["symbol"], "matches a real symbol")],
    )

    matches = guard.entry_matches()

    assert matches[0], "an entry covering a real symbol must not read as stale"


def test_removed_dead_entry_stays_removed():
    """Regression: the `row(for claim` fragment can never match an identifier."""
    fragments = [sym_frag for _file, sym_frag, _reason in guard.KNOWN_EXTENSIONS]

    assert not any("(" in fragment for fragment in fragments), (
        "a KNOWN_EXTENSIONS symbol fragment containing '(' cannot match a "
        "captured Swift identifier, so it is dead on arrival"
    )
