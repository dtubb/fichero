"""Unit tests for scripts/check_capability_scrapes.py.

Proves the capability-scrape ratchet guardrail (a) is clean against the real tree's
baseline and (b) actually CATCHES both directions of drift: a NEW file using the
AppSource capability-scrape idiom, and a baseline entry that no longer uses it (the
ratchet-shrink enforcement that stops the baseline growing back). Mutates temp copies
of the real tree rather than the tree itself.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_capability_scrapes.py"
_SPEC = importlib.util.spec_from_file_location("check_capability_scrapes", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]


def test_real_tree_matches_baseline():
    problems = _mod.check()
    assert problems == [], (
        "the real tree's AppSource capability-scrape idiom usage should exactly match "
        f"the checked-in baseline: {problems}"
    )


def test_new_scrape_file_is_caught(tmp_path):
    tests_dir = tmp_path / "fichero" / "Tests"
    tests_dir.mkdir(parents=True)
    scrape = tests_dir / "NewCapabilityScrapeTests.swift"
    scrape.write_text(
        """
        import XCTest

        final class NewCapabilityScrapeTests: XCTestCase {
            func testFeaturePresent() throws {
                let source = try AppSource.text("Views/Library/SomeView.swift")
                XCTAssertTrue(source.contains("New Feature"))
            }
        }
        """
    )

    original_tests_dir = _mod.TESTS_DIR
    original_root = _mod.ROOT
    _mod.TESTS_DIR = tests_dir
    _mod.ROOT = tmp_path
    try:
        current = _mod.scan()
        assert "fichero/Tests/NewCapabilityScrapeTests.swift" in current
        # Baseline (the real, checked-in one) does not know about this temp file, so
        # check() run over the temp tree must flag it as NEW.
        problems = _mod.check()
    finally:
        _mod.TESTS_DIR = original_tests_dir
        _mod.ROOT = original_root

    assert any("NewCapabilityScrapeTests.swift" in p and "NEW capability-scrape" in p for p in problems), problems


def test_baseline_entry_that_no_longer_scrapes_is_caught(tmp_path):
    """A baseline entry whose file has since dropped the AppSource/.contains( idiom
    (converted to a behavior test) must be flagged as ratchet drift — the guardrail
    forces the baseline to shrink, it can't silently keep a stale entry.
    """
    tests_dir = tmp_path / "fichero" / "Tests"
    tests_dir.mkdir(parents=True)
    converted = tests_dir / "ConvertedTests.swift"
    converted.write_text(
        """
        import XCTest

        final class ConvertedTests: XCTestCase {
            func testBehavior() throws {
                let result = SomeType().doSomething()
                XCTAssertEqual(result, .expected)
            }
        }
        """
    )

    original_tests_dir = _mod.TESTS_DIR
    original_root = _mod.ROOT
    original_baseline = _mod.BASELINE
    fake_baseline = tmp_path / "capability_scrapes_baseline.txt"
    fake_baseline.write_text("fichero/Tests/ConvertedTests.swift\n")
    _mod.TESTS_DIR = tests_dir
    _mod.ROOT = tmp_path
    _mod.BASELINE = fake_baseline
    try:
        problems = _mod.check()
    finally:
        _mod.TESTS_DIR = original_tests_dir
        _mod.ROOT = original_root
        _mod.BASELINE = original_baseline

    assert any("ConvertedTests.swift" in p and "ratchet drift" in p for p in problems), problems


def test_update_keeps_every_justification_and_says_when_it_drops_one(tmp_path):
    """`--update` must keep the `#` reasons a person wrote, where they wrote them (#5054).

    It used to regenerate the file from the tree, sorted, and drop every comment: a justification
    lasted only until someone ran the maintenance command the guard itself offers, and only the
    entries someone bothered to explain had anything to lose. Now a kept entry keeps its reason
    and its place, a new entry is appended, and a dropped entry that HAD a reason is reported.
    """
    original_baseline = _mod.BASELINE
    fake = tmp_path / "capability_scrapes_baseline.txt"
    fake.write_text(
        _mod.HEADER
        + "a/PlainTests.swift\n"
        + "\n# --- a section note\n"
        + "# why Kept is here\n"
        + "a/KeptTests.swift\n"
        + "# why Gone was here\n"
        + "a/GoneTests.swift\n"
    )
    _mod.BASELINE = fake
    try:
        dropped = _mod._write_baseline({"a/PlainTests.swift", "a/KeptTests.swift", "a/NewTests.swift"})
    finally:
        _mod.BASELINE = original_baseline

    assert fake.read_text() == (
        _mod.HEADER
        + "a/PlainTests.swift\n"
        + "\n# --- a section note\n"
        + "# why Kept is here\n"
        + "a/KeptTests.swift\n"
        + "a/NewTests.swift\n"
    )
    assert dropped == ["a/GoneTests.swift"]


def test_update_is_a_no_op_on_the_real_baseline():
    """Run on the real tree, `--update` must leave a current baseline byte-for-byte as it is:
    the 2026-09-30 baseline carries 30-odd hand-written reasons and section notes (#5054)."""
    before = _mod.BASELINE.read_text()
    try:
        _mod._write_baseline(_mod.scan())
        after = _mod.BASELINE.read_text()
    finally:
        _mod.BASELINE.write_text(before)
    assert after == before
