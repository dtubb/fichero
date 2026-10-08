"""`check_tool_outputs_declared`: every registered tool says what it writes (#5596).

Spec: `source.extract.every-output-declares-its-anchor` (source/source-model.md). The guard must
fail a tool with no declaration, fail an artifact-only tool that is not a seeded known gap, and
refuse a stale or issue-less baseline; it must pass a tool that declares where it attaches. The
last tests pin it to the real registry: every registered tool is declared, and the declarations
reach `ToolDef` and the tools list route's items.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_tool_outputs_declared.py"
_SPEC = importlib.util.spec_from_file_location("check_tool_outputs_declared", _SCRIPT)
assert _SPEC and _SPEC.loader
guard = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = guard
_SPEC.loader.exec_module(guard)  # type: ignore[attr-defined]

from fichero_server.workflows.tool_outputs import (  # noqa: E402
    ANCHORS,
    TOOL_OUTPUTS,
    WRITES,
    OutputDeclaration,
)


def _problems(names, declarations, known_gaps=None):
    return guard.problems(
        names, declarations, known_gaps or {},
        writes_vocabulary=WRITES, anchors_vocabulary=ANCHORS,
    )


def _decl(anchors_at: str, *writes: str) -> OutputDeclaration:
    return OutputDeclaration(frozenset(writes), anchors_at)


class TestFixtures:
    def test_an_undeclared_tool_fails(self):
        found = _problems(["new_tool"], {})
        assert len(found) == 1
        assert found[0].startswith("new_tool: registered with no output declaration")

    def test_an_artifact_only_tool_that_is_not_a_known_gap_fails(self):
        found = _problems(["summarise_page"], {"summarise_page": _decl("document", "artifact")})
        assert len(found) == 1
        assert "writes only an artifact" in found[0]

    def test_a_declared_tool_passes(self):
        declarations = {
            "read_lines": _decl("segment", "pass", "reading", "artifact"),
            "find_names": _decl("document", "mention", "statement"),
            "sources": _decl("none", "none"),
        }
        assert _problems(declarations, declarations) == []

    def test_an_artifact_only_tool_seeded_with_its_slice_issue_passes(self):
        declarations = {"translate": _decl("document", "artifact")}
        gaps = {"translate": "a translation becomes a reading (#5599)"}
        assert _problems(declarations, declarations, gaps) == []

    def test_a_known_gap_naming_no_slice_issue_fails(self):
        declarations = {"translate": _decl("document", "artifact")}
        for reason in ("later", "tracked in #1234"):
            found = _problems(declarations, declarations, {"translate": reason})
            assert found == [f"translate: known gap names no slice issue ({', '.join(sorted(guard.SLICE_ISSUES))})"]

    def test_a_known_gap_for_a_tool_that_now_attaches_fails_as_stale(self):
        declarations = {"translate": _decl("segment", "reading")}
        found = _problems(declarations, declarations, {"translate": "reading (#5599)"})
        assert found == ["translate: known gap but no longer artifact-only; remove it from the baseline"]

    def test_a_known_gap_or_declaration_for_an_unregistered_tool_fails(self):
        found = _problems([], {"gone": _decl("none", "none")}, {"gone2": "x (#5599)"})
        assert any(line.startswith("gone: declared") for line in found)
        assert any(line.startswith("gone2: known gap for a tool that is not registered") for line in found)

    @pytest.mark.parametrize(
        "declaration, expected",
        [
            (_decl("document", "artefact"), "writes outside the vocabulary"),
            (_decl("document"), "declares no writes"),
            (_decl("none", "none", "artifact"), "declares 'none' beside record kinds"),
            (_decl("line", "reading"), "anchors_at 'line' is not one of"),
        ],
    )
    def test_a_malformed_declaration_fails(self, declaration, expected):
        found = _problems(["tool"], {"tool": declaration})
        assert any(expected in line for line in found), found


class TestTheRealRegistry:
    def test_every_registered_tool_is_declared_and_the_baseline_holds(self):
        assert guard.main([]) == 0

    def test_the_baseline_is_the_artifact_only_tools_exactly(self):
        artifact_only = {name for name, d in TOOL_OUTPUTS.items() if d.writes == {"artifact"}}
        gaps = guard.load_known_gaps()
        assert set(gaps) == artifact_only
        assert json.loads(guard.KNOWN_GAPS_PATH.read_text(encoding="utf-8")) == gaps

    def test_reading_and_line_finding_declare_segments(self):
        """The review's inventory: line finding and reading reach the page as passes."""
        for name in ("detect_regions", "align_transcript", "merge_geometry", "transcribe"):
            assert {"pass", "reading"} <= TOOL_OUTPUTS[name].writes, name
            assert TOOL_OUTPUTS[name].anchors_at == "segment", name

    def test_the_declaration_reaches_the_tool_def(self):
        from fichero_server.workflows.registry import get_tool_def

        transcribe = get_tool_def("transcribe")
        assert transcribe is not None
        assert transcribe.writes == ["artifact", "page_text", "pass", "reading"]
        assert transcribe.anchors_at == "segment"
        assert get_tool_def("translate").writes == ["artifact"]

    def test_the_tools_list_route_serves_the_declaration(self):
        from fichero_server.api.routes.workflow.workflows import _tool_to_response
        from fichero_server.workflows.registry import get_tool_def

        response = _tool_to_response(get_tool_def("split_pages"))
        assert response.writes == ["node", "rendition"]
        assert response.anchors_at == "document"
