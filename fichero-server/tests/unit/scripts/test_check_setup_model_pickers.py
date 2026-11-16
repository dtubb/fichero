"""`scripts/check_setup_model_pickers.py` (`wide.picker.guard`, #6052): a model step with no picker, a no-model step that would
read like a model, a missing contract field and a stale allowlist entry each fail; the real registry passes."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_setup_model_pickers.py"
_SPEC = importlib.util.spec_from_file_location("check_setup_model_pickers", _SCRIPT)
assert _SPEC and _SPEC.loader
guard = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = guard
_SPEC.loader.exec_module(guard)


def scratch(**over):
    base = dict(stage_jobs=["read", "tie", "leave"], needs_a_model={"read": True, "tie": True, "leave": False},
                card_jobs={"read", "tie"}, text_jobs=set(), does_it={"leave"}, by_hand=set(), how={"leave": "rules"},
                contract_has_needs_a_model=True, allowlist={})
    base.update(over)
    return guard.problems(**base)


def test_a_scratch_registry_that_is_covered_passes():
    assert scratch() == []


def test_a_model_job_with_no_card_and_not_a_text_job_fails_and_an_allowlisted_one_passes():
    assert any("tie" in p and "no card" in p for p in scratch(card_jobs={"read"}))
    assert scratch(card_jobs={"read"}, text_jobs={"tie"}) == []
    assert scratch(card_jobs={"read"}, allowlist={"tie": "#1: its card waits"}) == []


def test_a_no_model_job_without_a_how_fails_and_a_by_hand_one_passes():
    assert any("leave" in p for p in scratch(how={"leave": None}))
    assert any("leave" in p for p in scratch(does_it=set()))
    assert scratch(does_it=set(), by_hand={"leave"}, how={}) == []


def test_a_missing_needs_a_model_in_the_contract_fails():
    assert any("needs_a_model" in p for p in scratch(contract_has_needs_a_model=False))


def test_a_stale_allowlist_entry_fails():
    assert any("stale" in p for p in scratch(allowlist={"read": "#1: waits"}))  # it has a card now
    assert any("stale" in p for p in scratch(allowlist={"leave": "#1: waits"}))  # it says how now
    assert any("stale" in p for p in scratch(allowlist={"ghost": "#1: gone"}))  # not a job


def test_the_real_registry_passes_with_an_empty_allowlist():
    assert guard.NO_PICKER_YET == {}
    assert guard.problems(**guard._facts()) == []
