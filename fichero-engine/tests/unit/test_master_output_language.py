"""Every output-language resolution honours the master language (#4172).

Daniel: SVO statements come out in inconsistent languages. One cause needed no
LLM misbehaviour at all — `default_primary_language` is an app setting that
beats auto-detect, but only ONE of the three tools that resolve an output
language was passing it. `extractors.py` (SVO/entity extraction) and
`catalogue.py` (catalogue entries) both auto-detected per chunk instead, so the
same library drifted depending on which path ran.

The AST test is the important one: it fails for a call site that does not exist
yet, which is how this regressed in the first place.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from fichero.llm import lang_detect

ENGINE_SRC = Path(__file__).resolve().parents[2] / "src" / "fichero"


def _resolve_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text())
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", getattr(node.func, "attr", None)) == "resolve_output_language"
    ]


def test_every_resolve_output_language_call_passes_primary_language():
    """A call site that omits it silently reverts to per-chunk auto-detect."""
    offenders: list[str] = []
    for path in sorted(ENGINE_SRC.rglob("*.py")):
        for call in _resolve_calls(path):
            if not any(kw.arg == "primary_language" for kw in call.keywords):
                offenders.append(f"{path.relative_to(ENGINE_SRC)}:{call.lineno}")

    assert not offenders, (
        "resolve_output_language() called without primary_language — the master "
        "language will be ignored on this path:\n  " + "\n  ".join(offenders)
    )


def test_all_three_known_tools_are_covered():
    """Guards the AST test itself: if the calls moved, this notices."""
    covered = {
        path.relative_to(ENGINE_SRC).as_posix()
        for path in sorted(ENGINE_SRC.rglob("*.py"))
        if _resolve_calls(path)
    }

    assert covered == {
        "workflows/tools/extractors.py",
        "workflows/tools/extract_all.py",
        "workflows/tools/catalogue.py",
    }, f"resolve_output_language call sites moved: {sorted(covered)}"


class TestConfiguredPrimaryLanguage:
    def test_returns_the_configured_setting(self, monkeypatch):
        class _DB:
            def get_setting(self, key):
                assert key == "default_primary_language"
                return "Spanish"

        monkeypatch.setattr("fichero.db.app.get_app_db", lambda: _DB())

        assert lang_detect.configured_primary_language() == "Spanish"

    def test_returns_none_when_unset(self, monkeypatch):
        class _DB:
            def get_setting(self, key):
                return None

        monkeypatch.setattr("fichero.db.app.get_app_db", lambda: _DB())

        assert lang_detect.configured_primary_language() is None


class TestPrecedenceIsUnchanged:
    """The documented order must not regress: explicit > master > auto-detect."""

    SPANISH = "El documento describe el caso del señor Antonio Asprilla."

    def test_explicit_workflow_language_beats_master_language(self):
        assert (
            lang_detect.resolve_output_language(
                "English", self.SPANISH, primary_language="Spanish"
            )
            == "English"
        )

    def test_master_language_beats_auto_detect(self):
        assert (
            lang_detect.resolve_output_language(
                "auto", self.SPANISH, primary_language="French"
            )
            == "French"
        )

    @pytest.mark.parametrize("unset", [None, "", "   "])
    def test_unset_master_language_falls_through_to_detection(self, unset):
        assert (
            lang_detect.resolve_output_language("auto", self.SPANISH, primary_language=unset)
            == "Spanish"
        )
