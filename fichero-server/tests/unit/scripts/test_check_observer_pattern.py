"""What `check_observer_pattern` may flag, and what its backlog must say.

It had no test. Its ten backlog entries all carried one pasted reason naming three
anti-patterns ("globalLibrary / client.api. / FeatureManager") when every one of them has
exactly one, `LibraryManager.shared.globalLibrary`. Read per file, two used the global
library as their ONLY source, and one of those WRITES to it (#5133).
"""
from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_observer_pattern.py"
_SPEC = importlib.util.spec_from_file_location("check_observer_pattern", _SCRIPT)
assert _SPEC and _SPEC.loader
obs = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = obs
_SPEC.loader.exec_module(obs)  # type: ignore[attr-defined]


def _patterns(swift: str) -> list[str]:
    return obs._detect_patterns(obs.code_only(swift))


def test_a_view_reaching_the_global_library_is_flagged():
    """If this fails, a view can silently read the reserved global library instead of the
    one its window is showing — the #4461 wrong-library defect."""
    src = "func load() async { let s = LibraryManager.shared.globalLibrary?.entityService }\n"
    assert "direct-library-manager" in _patterns(src)


def test_a_preview_or_comment_mention_is_not_flagged():
    """Over-fire check: preview scaffolding and prose that NAMES the defect (several files
    document why they stopped using it) are not uses of it."""
    src = (
        "/// It resolved `LibraryManager.shared.globalLibrary`, the wrong library.\n"
        "struct V: View { var body: some View { Text(\"x\") } }\n"
        "#Preview {\n    V().environment(LibraryManager.shared.globalLibrary!.entityService)\n}\n"
    )
    assert _patterns(src) == []


def test_every_backlog_entry_says_why_in_its_own_words():
    """A reason pasted across entries is a permission, not a reason. The one repeated
    reason allowed is the FALLBACK finding, the same observation about each file."""
    counts = Counter(obs.KNOWN_VIOLATIONS.values())
    pasted = {r: n for r, n in counts.items() if n > 1 and not r.startswith("FALLBACK")}
    assert pasted == {}, pasted


def test_the_backlog_describes_the_tree():
    """Every entry is still an offender, and every offender is listed."""
    found = set(obs.scan())
    assert set(obs.KNOWN_VIOLATIONS) == found
