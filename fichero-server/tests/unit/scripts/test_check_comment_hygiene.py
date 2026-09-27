"""What check_comment_hygiene may call commented-out code.

It had no test. Its rule matched any of `= ; { }` anywhere in a comment line, and any Swift
keyword after whitespace — so it fired on this codebase's own documented commenting style:
prose that cites an identifier, names a caller as `File.swift:169-181`, ends a sentence in a
parenthetical, lists enum cases as `.widescreen → …`, or uses "for", "class" or "import" in an
ordinary sentence. Eleven of its fourteen allowlist entries said exactly that — "false positive
(prose)" — which is eleven people writing the missing rule down instead of adding it.

A hygiene rule that cannot tell a commented-out `store.reload()` from a sentence about
reloading is worse than no rule: it teaches people to stop explaining their decisions, which is
the opposite of what this repository asks for. So the rule is tested in BOTH directions, and the
prose cases below are real lines from the app, not invented ones.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_comment_hygiene.py"
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC = importlib.util.spec_from_file_location("check_comment_hygiene", _SCRIPT)
assert _SPEC and _SPEC.loader
hygiene = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = hygiene
_SPEC.loader.exec_module(hygiene)  # type: ignore[attr-defined]


def _codeish(line: str) -> bool:
    return bool(hygiene._CODEISH.search(line))


REAL_SWIFT = [
    "let store = library.documentStore",
    "if let doc = selection.first {",
    "store.reload()",
    "}",
    "documentStore.reload(force: true)",
    "@State private var count = 0",
    "guard let id = doc.id else { return }",
    "return AlignTranscriptResponse(",
]

#: Lifted verbatim from the app. Each one was being reported as commented-out code.
REAL_PROSE = [
    "The percentage on the right says how well a row matched. It never said",
    '* "exact"  — the literal words are in this document (`fulltext`)',
    '.widescreen → list and preview side-by-side  → "Show Side Preview"',
    "which says nothing about what THIS particular selected row is and",
    '("<doc>:entity:<id>"/"<doc>:claim:<id>") leak into code built for',
    "already focuses this row with the bare `entity.id` — this",
    "The engine rides `metadata.match_sources` on every hit. The legs that add",
    "menu offers Relevance exactly when the toolbar's does — and",
]


class TestTheRuleSeparatesCodeFromProse:
    @pytest.mark.parametrize("line", REAL_SWIFT)
    def test_a_swift_statement_is_code(self, line):
        assert _codeish(line), line

    @pytest.mark.parametrize("line", REAL_PROSE)
    def test_a_real_prose_line_from_the_app_is_not_code(self, line):
        assert not _codeish(line), line

    def test_a_keyword_inside_a_sentence_is_not_code(self):
        """The old rule matched `(^|\\s)for\\b` anywhere, so this read as a loop."""
        assert not _codeish("a bare id. Also fixes a case the old ambient flag never covered")
        assert not _codeish("used to fall straight into the document-promotion path below")

    def test_a_trailing_parenthesis_is_not_enough(self):
        """Dropped on purpose: prose here ends in a parenthetical constantly."""
        assert not _codeish("the same value, not a second writer (see #4850)")

    def test_a_trailing_brace_still_is(self):
        assert _codeish("for row in rows {")

    def test_an_empty_comment_line_is_neither(self):
        assert not _codeish("")
        assert not _codeish("   ")


class TestTheAllowlistIsNoLongerMostlyWorkaround:
    def test_the_guard_passes_on_the_repo(self):
        found = hygiene.scan()
        unaccounted = sorted(set(found) - set(hygiene.KNOWN_VIOLATIONS))
        assert unaccounted == [], unaccounted

    def test_it_shrank_from_fourteen_to_one(self):
        """Thirteen of the fourteen were the code-like rule firing on prose."""
        assert len(hygiene.KNOWN_VIOLATIONS) == 1

    def test_the_surviving_entry_is_the_other_rule_entirely(self):
        """An untracked TODO, not a prose false positive — which is a real finding."""
        (reason,) = hygiene.KNOWN_VIOLATIONS.values()
        assert "TODO" in reason

    def test_a_commented_out_block_is_still_caught(self):
        """The rule has to keep working, or clearing the allowlist was just going blind."""
        block = [
            "let store = library.documentStore",
            "store.reload(force: true)",
            "documentStore.splice(changes)",
        ]
        found: dict[str, str] = {}
        hygiene._flush_block(_SCRIPT, 1, block, found)
        assert found, "three consecutive Swift statements must still be reported"
