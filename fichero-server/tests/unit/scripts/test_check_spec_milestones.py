"""Unit tests for scripts/check_spec_milestones.py.

Proves the spec<->milestone rule: an APPROVED spec must declare `Milestone: <name>`; DRAFT and
grandfathered specs are exempt. Runs OFFLINE (the live GitHub check is stubbed out).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_spec_milestones.py"
_SPEC = importlib.util.spec_from_file_location("check_spec_milestones", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

APPROVED_WITH = """# X — Design Spec

> Milestone: my-surface

> Design-led. **Status: APPROVED — 2026-09-09.**
"""
APPROVED_WITHOUT = """# Y — Design Spec

> Design-led. **Status: APPROVED — 2026-09-09.**
"""
DRAFT_WITHOUT = """# Z — Design Spec

> Design-led. **Status: DRAFT — awaiting approval.**
"""


def _seed(tmp_path: Path, name: str, body: str) -> None:
    (tmp_path / name).write_text(body, encoding="utf-8")


def _run(tmp_path: Path, monkeypatch) -> int:
    monkeypatch.setattr(_mod, "SPECS_DIR", tmp_path)
    monkeypatch.setattr(_mod, "_live_milestones", lambda: None)  # offline
    return _mod.main()


def test_approved_with_milestone_passes(tmp_path, monkeypatch):
    _seed(tmp_path, "a.md", APPROVED_WITH)
    assert _run(tmp_path, monkeypatch) == 0


def test_approved_without_milestone_fails(tmp_path, monkeypatch):
    _seed(tmp_path, "b.md", APPROVED_WITHOUT)
    assert _run(tmp_path, monkeypatch) == 1


def test_draft_without_milestone_passes(tmp_path, monkeypatch):
    _seed(tmp_path, "c.md", DRAFT_WITHOUT)
    assert _run(tmp_path, monkeypatch) == 0


def test_grandfathered_without_milestone_passes(tmp_path, monkeypatch):
    # A grandfathered stem is exempt even though APPROVED + no milestone.
    stem = next(iter(_mod.MILESTONE_GRANDFATHERED))
    _seed(tmp_path, f"{stem}.md", APPROVED_WITHOUT)
    assert _run(tmp_path, monkeypatch) == 0


def test_scaffold_is_ignored(tmp_path, monkeypatch):
    _seed(tmp_path, "_TEMPLATE.md", APPROVED_WITHOUT)  # underscore = scaffold
    assert _run(tmp_path, monkeypatch) == 0


def test_real_specs_pass_offline(monkeypatch):
    # The real specs dir, offline, must be green (grandfathered + declared).
    monkeypatch.setattr(_mod, "_live_milestones", lambda: None)
    assert _mod.main() == 0
