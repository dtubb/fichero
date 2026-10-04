"""scripts/apply_triage.py writes a triaged issue into its spec without disturbing the spec.

WHY: backlog triage turns old issues into spec behaviours (or Future ideas) in bulk. If a line lands
in the wrong section, or is written twice, specs fill with noise and the guards stop meaning anything.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "apply_triage.py"
_SPEC = importlib.util.spec_from_file_location("apply_triage", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)


def test_lines_land_in_their_section_once_and_the_rest_is_untouched(tmp_path):
    spec = tmp_path / "s.md"
    spec.write_text("# S\n\n## Behaviors\n- `a` — **[OK]** x\n\n## Open questions\nq\n")
    _mod.add_under(spec, _mod.FUTURE, "- (#1) an idea")
    _mod.add_under(spec, _mod.TRIAGED, "- `b` — **[GAP]** (#2) y")
    _mod.add_under(spec, _mod.FUTURE, "- (#3) another")
    _mod.add_under(spec, _mod.FUTURE, "- (#1) an idea")  # written twice: kept once
    text = spec.read_text()
    assert text.startswith("# S\n\n## Behaviors\n- `a` — **[OK]** x\n\n## Open questions\nq\n")
    future = text.split(_mod.FUTURE)[1].split("\n## ")[0]
    assert future.count("(#1)") == 1 and "(#3)" in future and "(#2)" not in future
    assert "- `b` — **[GAP]** (#2) y" in text.split(_mod.TRIAGED)[1]


def test_an_issue_covered_by_an_existing_behaviour_is_cited_on_its_tag_line(tmp_path):
    spec = tmp_path / "s.md"
    spec.write_text("- `a.b` — **[GAP]** (#10) x\n- `c.d` — **[PARTIAL]** y\n")
    assert _mod.cite_on(spec, "a.b", "20") and _mod.cite_on(spec, "c.d", "30")
    assert _mod.cite_on(spec, "a.b", "20")  # citing twice changes nothing
    assert spec.read_text() == "- `a.b` — **[GAP]** (#20, #10) x\n- `c.d` — **[PARTIAL]** (#30) y\n"
    assert not _mod.cite_on(spec, "missing.id", "40")
