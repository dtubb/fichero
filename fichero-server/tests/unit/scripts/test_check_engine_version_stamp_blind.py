"""A guardrail must know when it has gone blind, and say so (#4382).

On 2026-09-27 the seven AppState files moved into `App/AppState/`. This script's READINESS
constant still named the old path, and it did not fail — it raised FileNotFoundError from
inside `failures()`. A traceback reads as neither pass nor fail: a sweep records a non-zero
exit and the reader learns nothing about what to repoint. Three sibling guards and four tests
were pinned to the same moved paths; this was the only one that crashed rather than reported.

These tests fail if the blind path stops firing, so the next file move gets a sentence instead
of a stack trace.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_engine_version_stamp.py"
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC = importlib.util.spec_from_file_location("check_engine_version_stamp", _SCRIPT)
assert _SPEC and _SPEC.loader
stamp = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = stamp
_SPEC.loader.exec_module(stamp)  # type: ignore[attr-defined]


class TestItReportsAMovedInputInsteadOfCrashing:
    def test_nothing_is_blind_on_the_tree_as_it_stands(self):
        """If this fails, an input moved and the constant beside it needs repointing."""
        assert stamp.blind_inputs() == []

    def test_a_moved_input_is_named_with_its_constant(self, monkeypatch):
        """The message has to name the CONSTANT, not just the path — that is what gets edited."""
        monkeypatch.setattr(stamp, "READINESS", stamp.ROOT / "fichero" / "gone.swift")
        blind = stamp.blind_inputs()
        assert len(blind) == 1
        assert blind[0].startswith("READINESS -> ")
        assert "gone.swift" in blind[0]

    def test_main_exits_2_and_does_not_raise(self, monkeypatch, capsys):
        """2, not 1: a check that cannot answer is not the same as a check that failed.

        The old behaviour was an exception, which is why the stale path survived a sweep.
        """
        monkeypatch.setattr(stamp, "READINESS", stamp.ROOT / "fichero" / "gone.swift")
        monkeypatch.setattr(sys, "argv", ["check_engine_version_stamp.py"])
        assert stamp.main() == 2
        assert "BLIND" in capsys.readouterr().err

    def test_every_declared_input_is_a_real_module_constant(self):
        """REQUIRED_INPUTS is looked up by name, so a typo would silently check nothing."""
        for name in stamp.REQUIRED_INPUTS:
            assert isinstance(getattr(stamp, name), Path), name
