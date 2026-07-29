"""Unit tests for scripts/check_app_intent_action_coverage.py (#2281)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[4] / "scripts" / "check_app_intent_action_coverage.py"
)
_SPEC = importlib.util.spec_from_file_location("check_app_intent_action_coverage", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

registered_actions = _mod.registered_actions
violations = _mod.violations


def _engine(tmp_path: Path, body: str) -> Path:
    d = tmp_path / "engine"
    d.mkdir()
    (d / "routes.py").write_text(body)
    return d


def _intents(tmp_path: Path, body: str) -> Path:
    d = tmp_path / "Intents"
    d.mkdir()
    (d / "FicheroActionIntents.swift").write_text(body)
    return d


def test_extracts_registered_actions(tmp_path):
    eng = _engine(tmp_path, '@action("entity.merge")\ndef m(): ...\n@action("note.create", undo=True)\ndef n(): ...\n')
    assert registered_actions(eng) == {"entity.merge", "note.create"}


def test_resolved_reference_is_clean(tmp_path):
    eng = _engine(tmp_path, '@action("entity.merge")\ndef m(): ...\n')
    intents = _intents(tmp_path, '_ = try await invokeAuditedAction("entity.merge", params: p)\n')
    assert not violations(engine_dir=eng, intents_dir=intents)


def test_unresolved_reference_is_drift(tmp_path):
    eng = _engine(tmp_path, '@action("entity.merge")\ndef m(): ...\n')
    # Intent invokes a renamed-away action.
    intents = _intents(tmp_path, '_ = try await invokeAuditedAction("entity.combine", params: p)\n')
    bad = violations(engine_dir=eng, intents_dir=intents)
    assert any("entity.combine" in k for k in bad), "stale App Intent action must be flagged"


def test_real_tree_clean():
    assert not violations(), "every shipped App Intent action must resolve to a registered action"
