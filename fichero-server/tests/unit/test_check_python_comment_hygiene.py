"""Unit tests for scripts/check_python_comment_hygiene.py (#1915)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_python_comment_hygiene.py"
_SPEC = importlib.util.spec_from_file_location("check_python_comment_hygiene", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

scan = _mod.scan


# ---------------------------------------------------------------------------
# Synthetic fixture helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Commented-out code block detection
# ---------------------------------------------------------------------------

def test_flags_three_consecutive_keyword_comment_lines(tmp_path):
    _write(tmp_path, "dead.py", """\
x = 1
# def foo():
#     return 42
# import os
""")
    found = scan(tmp_path)
    assert found, "should flag a 3-line commented-out code block"


def test_ignores_two_consecutive_keyword_comment_lines(tmp_path):
    _write(tmp_path, "ok.py", """\
x = 1
# def foo():
#     return 42
y = 2
""")
    found = scan(tmp_path)
    code_violations = {k: v for k, v in found.items() if "commented-out" in v}
    assert not code_violations, "two keyword comment lines should not be flagged"


def test_ignores_prose_comments_mentioning_keywords(tmp_path):
    _write(tmp_path, "prose.py", """\
# This module defines the routing logic.
# We use return values to signal errors.
# Classes are registered at import time.
""")
    found = scan(tmp_path)
    # Prose lines don't start the body with a Python keyword — no flag
    code_violations = {k: v for k, v in found.items() if "commented-out" in v}
    assert not code_violations, "prose-only comment block should not be flagged"


# ---------------------------------------------------------------------------
# TODO / FIXME without issue ref
# ---------------------------------------------------------------------------

def test_flags_todo_without_issue_ref(tmp_path):
    _write(tmp_path, "todo.py", "# TODO: fix this someday\n")
    found = scan(tmp_path)
    todo_violations = {k: v for k, v in found.items() if "TODO" in v or "FIXME" in v}
    assert todo_violations, "bare TODO should be flagged"


def test_flags_fixme_without_issue_ref(tmp_path):
    _write(tmp_path, "fixme.py", "# FIXME: broken path\n")
    found = scan(tmp_path)
    assert found


def test_ignores_todo_with_issue_ref(tmp_path):
    _write(tmp_path, "ok_todo.py", "# TODO(#1234): tracked in GitHub\n")
    found = scan(tmp_path)
    assert not found, "TODO with #NNN should be exempt"


def test_ignores_todo_with_bare_hash_number(tmp_path):
    _write(tmp_path, "ok_todo2.py", "# TODO #99: also tracked\n")
    found = scan(tmp_path)
    assert not found


# ---------------------------------------------------------------------------
# Banner / divider detection
# ---------------------------------------------------------------------------

def test_flags_long_banner_block(tmp_path):
    banner = "\n".join(f"# {'---' * 10}" for _ in range(8)) + "\n"
    _write(tmp_path, "banner.py", banner)
    found = scan(tmp_path)
    banner_violations = {k: v for k, v in found.items() if "banner" in v}
    assert banner_violations, "8-line punctuation banner should be flagged"


def test_ignores_short_banner(tmp_path):
    banner = "\n".join(f"# {'---' * 10}" for _ in range(5)) + "\n"
    _write(tmp_path, "short_banner.py", banner)
    found = scan(tmp_path)
    banner_violations = {k: v for k, v in found.items() if "banner" in v}
    assert not banner_violations, "fewer than 8 banner lines should not be flagged"


# ---------------------------------------------------------------------------
# Real repo gate
# ---------------------------------------------------------------------------

def test_repo_python_source_has_no_new_violations():
    """The real backend source must have no unallowlisted violations."""
    found = scan()
    known = set(_mod.KNOWN_VIOLATIONS)
    new = set(found) - known
    assert not new, (
        "New Python comment hygiene violations found (add to KNOWN_VIOLATIONS "
        "or fix the source):\n" + "\n".join(f"  {k}: {found[k]}" for k in sorted(new))
    )


def test_known_violations_are_not_stale():
    """Every KNOWN_VIOLATIONS entry must still appear in the real scan."""
    found = scan()
    stale = set(_mod.KNOWN_VIOLATIONS) - set(found)
    assert not stale, (
        f"Stale KNOWN_VIOLATIONS entries (violations are fixed — remove them): {stale}"
    )
