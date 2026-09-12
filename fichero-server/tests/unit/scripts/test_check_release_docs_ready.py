"""Release-docs readiness guardrail (release lane step 3).

Proves `docs_ready()` in both directions without touching the real
RELEASE_NOTES.md/CHANGELOG.md or running the (slow, network-adjacent)
freshness scripts: a version missing its RELEASE_NOTES section is reported as
not ready, and a version present in both files passes clean.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[4] / "scripts" / "check_release_docs_ready.py"
)
_SPEC = importlib.util.spec_from_file_location("check_release_docs_ready", _SCRIPT)
assert _SPEC and _SPEC.loader
check_release_docs_ready = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_release_docs_ready
_SPEC.loader.exec_module(check_release_docs_ready)  # type: ignore[attr-defined]

docs_ready = check_release_docs_ready.docs_ready
_version_to_changelog_date = check_release_docs_ready._version_to_changelog_date


def test_version_to_changelog_date_converts_dots_to_dashes():
    assert _version_to_changelog_date("2026.09.08") == "2026-09-08"
    assert _version_to_changelog_date("2026.09.08.2") == "2026-09-08"
    assert _version_to_changelog_date("2026.09.08-beta") == "2026-09-08"


def test_missing_release_notes_section_fails():
    """A version whose RELEASE_NOTES section is absent is reported not-ready."""
    notes = "# Release Notes\n\n## 2026.09.07\n\nEarlier release prose.\n"
    changelog = "# Changelog\n\n## 2026-09-08\n\n- fix(x): something\n"

    problems = docs_ready("2026.09.08", notes, changelog)

    assert any("RELEASE_NOTES.md" in p for p in problems)


def test_missing_changelog_section_fails():
    """A version whose CHANGELOG day entry is absent is reported not-ready."""
    notes = "# Release Notes\n\n## 2026.09.08\n\nShip-day prose.\n"
    changelog = "# Changelog\n\n## 2026-09-07\n\n- fix(x): something\n"

    problems = docs_ready("2026.09.08", notes, changelog)

    assert any("CHANGELOG.md" in p for p in problems)


def test_empty_sections_fail_even_when_present():
    notes = "# Release Notes\n\n## 2026.09.08\n\n## 2026.09.07\n\nOlder prose.\n"
    changelog = "# Changelog\n\n## 2026-09-08\n\n## 2026-09-07\n\n- fix(x): y\n"

    problems = docs_ready("2026.09.08", notes, changelog)

    assert any("empty" in p for p in problems)


def test_version_present_in_both_files_passes():
    """A version present with non-empty prose in both files reports no problems."""
    notes = (
        "# Release Notes\n\n"
        "## 2026.09.08\n\n"
        "Ship-day prose describing what changed.\n\n"
        "## 2026.09.07\n\nEarlier release.\n"
    )
    changelog = (
        "# Changelog\n\n"
        "## 2026-09-08\n\n"
        "- fix(x): something\n\n"
        "## 2026-09-07\n\n- fix(y): something else\n"
    )

    problems = docs_ready("2026.09.08", notes, changelog)

    assert problems == []
