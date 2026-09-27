"""What `check_undo_coverage` may count as an undo registration.

It had no test, and it reported six endpoints as covered that nothing anywhere undoes: each
one matched a substring of its path inside a comment in a file that happens to mention
UndoManager. `POST /api/library` passed on the comment "document/library undo". The guard now
matches strictly, and the answer it gives is zero of 393 — see #5109 for why that number is a
statement about the app, not about the guard.

These tests fail if the loose match comes back, and if the honest zero is ever quietly
re-inflated by a matcher change rather than by undo being built.
"""
from __future__ import annotations

import functools
import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_undo_coverage.py"
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC = importlib.util.spec_from_file_location("check_undo_coverage", _SCRIPT)
assert _SPEC and _SPEC.loader
check_undo_coverage = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_undo_coverage
_SPEC.loader.exec_module(check_undo_coverage)  # type: ignore[attr-defined]


@functools.lru_cache(maxsize=1)
def _rows() -> tuple:
    return tuple(check_undo_coverage.scan())


class TestTheSixFalsePositives:
    """Each of these was reported as having undo. None of them has any."""

    def test_no_mutating_endpoint_is_reported_as_having_undo(self):
        """Zero is the honest answer while undo is view-level.

        If this ever passes with a non-zero count, either undo grew an endpoint axis — in
        which case #5109 got decided and this test should say which way — or the matcher
        went loose again.
        """
        covered = [row.endpoint for row in _rows() if row.undo_registered]
        assert covered == [], covered

    def test_the_library_endpoint_is_not_covered_by_a_comment_about_library_undo(self):
        """UndoRouting.swift:46 reads "document/library undo"; `/library` matched inside it."""
        rows = {row.endpoint: row for row in _rows()}
        assert rows["POST /api/library"].undo_registered is False
        assert rows["POST /api/library"].evidence == ()

    def test_the_pairing_endpoint_is_not_covered_by_the_word_pairing(self):
        rows = {row.endpoint: row for row in _rows()}
        assert rows["POST /api/pair"].undo_registered is False

    def test_all_six_are_seeded_with_the_reason_they_stopped_passing(self):
        """A seeded gap has to say why, or the next reader cannot tell it from a deferral."""
        for endpoint in (
            "POST /api/actions",
            "POST /api/actions/invoke",
            "POST /api/authz/share",
            "POST /api/library",
            "POST /api/pair",
            "POST /api/workflows",
        ):
            reason = check_undo_coverage.KNOWN_GAPS[endpoint]
            assert "#5109" in reason, endpoint
            assert "comment" in reason, endpoint


class TestTheScanStillSeesTheWholeSurface:
    def test_the_mutating_population_is_unchanged_by_the_stricter_match(self):
        """The fix tightened the witness, not the population: 393 mutating operations when it
        landed. A FLOOR, not an equality -- pinned exactly, this failed the day PATCH
        /api/segments was added (394), which is the surface growing, not the scan going blind.
        What must never happen is the count FALLING, because that means the scan stopped
        seeing routes it used to see and every "0 of N" figure quietly shrinks with it."""
        assert len(_rows()) >= 393

    def test_undo_registering_files_are_still_found(self):
        """If this drops to zero the guard has gone blind, which is worse than red."""
        assert len(check_undo_coverage.UNDO_SOURCES) >= 8
