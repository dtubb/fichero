"""Unit tests for scripts/check_spec_broken_has_issue.py.

Proves the rule (creative director, 2026-09-18): every spec behavior tagged
[BROKEN]/[GAP]/[GAP/BROKEN]/[PARTIAL]/[MISSING] must cite a tracking issue (`#1234` or a
superseding `→ #1234`), on the tag line itself or an indented continuation line. [OK] lines
are exempt. Runs OFFLINE — pure file-text parsing, no network.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_spec_broken_has_issue.py"
_SPEC = importlib.util.spec_from_file_location("check_spec_broken_has_issue", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

WITH_ISSUE = """# Spec

- `panes.split.asymmetric` — **[GAP/BROKEN]** splitting a preview vertically then horizontally
  does not stay independent. (#4712)
"""

WITHOUT_ISSUE = """# Spec

- `panes.chat.below-sidebar` — **[BROKEN]** the chat history and its input live in the left
  sidebar instead of a dockable pane.
"""

CONTINUATION_HAS_ISSUE = """# Spec

- `panes.head.kind-switcher-everywhere` — **[BROKEN]** every pane head that renders a leaf
  kind mounts the kind selector. Today only Library and Preview do. (#4706, reported 2026-09-18)
  See also the guardrail test for `selectableKinds`.
"""

SUPERSEDED_BY_EPIC = """# Spec

- `panes.kg.one-view-system` — **[BROKEN]** the entities view and the claims view are the
  same underlying list. (→ #4705 increment 3)
"""

OK_LINE_IGNORED = """# Spec

- `panes.split.focused-only` — **[OK]** splitting a pane splits only the focused pane.
"""

PATH_BULLET_IGNORED = """# Spec

- `agent-work/reviews/2026-08-02-node-editor-fabel-review.md` — **superseded**
  for its Finding 1, carried into the spec above as `[BROKEN]`/`[BROKEN-partial]`
  surface-shaped.
"""

SYMBOL_BULLET_IGNORED = """# Spec

- `ChatView` is a RAG chat view with tabs.
  - **Correctness risk:** something here names it a **[BROKEN]** duplicate but
    the tag belongs to the nested behavior below, not to `ChatView`.
  - `m2p.chat-scope-inspector-only` flags this as a **[BROKEN]** duplicate. (#4719)
"""


def _seed(tmp_path: Path, body: str, rel: str = "ui/example.md") -> Path:
    specs_root = tmp_path / "docs" / "contributor_manual" / "specs"
    p = specs_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return specs_root


def _run(tmp_path: Path, body: str, monkeypatch, rel: str = "ui/example.md") -> int:
    specs_dir = _seed(tmp_path, body, rel)
    monkeypatch.setattr(_mod, "SPECS_DIR", specs_dir)
    monkeypatch.setattr(_mod, "GRANDFATHERED_FILES", set())
    return _mod.main()


def test_tagged_line_with_issue_passes(tmp_path, monkeypatch):
    assert _run(tmp_path, WITH_ISSUE, monkeypatch) == 0


def test_tagged_line_without_issue_fails(tmp_path, monkeypatch):
    assert _run(tmp_path, WITHOUT_ISSUE, monkeypatch) == 1


def test_continuation_line_issue_ref_counts(tmp_path, monkeypatch):
    assert _run(tmp_path, CONTINUATION_HAS_ISSUE, monkeypatch) == 0


def test_superseded_by_epic_increment_passes(tmp_path, monkeypatch):
    assert _run(tmp_path, SUPERSEDED_BY_EPIC, monkeypatch) == 0


def test_ok_line_is_ignored(tmp_path, monkeypatch):
    assert _run(tmp_path, OK_LINE_IGNORED, monkeypatch) == 0


def test_empty_spec_dir_exits_2(tmp_path, monkeypatch):
    empty = tmp_path / "empty_specs"
    empty.mkdir()
    monkeypatch.setattr(_mod, "SPECS_DIR", empty / "does_not_exist")
    assert _mod.main() == 2


def test_file_path_bullet_is_not_a_behavior_id(tmp_path, monkeypatch):
    # A backticked FILE PATH (contains "/") is never a behavior id, even if the surrounding
    # prose mentions a bracketed tag like [BROKEN] — that tag describes something ELSE.
    assert _run(tmp_path, PATH_BULLET_IGNORED, monkeypatch) == 0


def test_symbol_bullet_is_not_a_behavior_id_and_does_not_swallow_nested_tag(tmp_path, monkeypatch):
    # `ChatView` (capitalized, no dot) is a Swift symbol, not a behavior id — its bullet is
    # skipped. The nested `m2p.chat-scope-inspector-only` sub-bullet starts its own block (not
    # swallowed into ChatView's), and it cites #4719, so the whole file is clean.
    assert _run(tmp_path, SYMBOL_BULLET_IGNORED, monkeypatch) == 0


def test_grandfathered_file_with_debt_passes_and_is_counted(tmp_path, monkeypatch):
    specs_dir = _seed(tmp_path, WITHOUT_ISSUE, "kg/kg-tables.md")
    monkeypatch.setattr(_mod, "SPECS_DIR", specs_dir)
    monkeypatch.setattr(_mod, "GRANDFATHERED_FILES", {"kg/kg-tables.md"})
    assert _mod.main() == 0


def test_clean_grandfathered_file_fails_remove_from_list(tmp_path, monkeypatch):
    # The grandfather list only shrinks: a file with zero remaining untracked debt must be
    # removed by whoever cleared it, or the gate catches the stale entry.
    specs_dir = _seed(tmp_path, WITH_ISSUE, "kg/kg-tables.md")
    monkeypatch.setattr(_mod, "SPECS_DIR", specs_dir)
    monkeypatch.setattr(_mod, "GRANDFATHERED_FILES", {"kg/kg-tables.md"})
    assert _mod.main() == 1


def test_non_grandfathered_debt_fails(tmp_path, monkeypatch):
    specs_dir = _seed(tmp_path, WITHOUT_ISSUE, "kg/kg-tables.md")
    monkeypatch.setattr(_mod, "SPECS_DIR", specs_dir)
    monkeypatch.setattr(_mod, "GRANDFATHERED_FILES", set())
    assert _mod.main() == 1
