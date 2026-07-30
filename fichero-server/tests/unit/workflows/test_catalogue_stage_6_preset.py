"""'6 · Catalogue' — the final act as its own re-runnable stage (#4423).

Stages `1 ·` … `5 ·` shipped as individually runnable presets. The catalogue
write — the thing the whole pipeline exists to produce — existed ONLY inside
the 12-node `Catalogue` composite. So asking for a catalogue on material whose
earlier stages were already done and CORRECTED re-ran all five stages over
those corrections.

Verified before adding anything, as the issue asks: stage 5 is
`files → kg_persist_finalize` and nothing more. The `catalogue` tool appears in
no stage preset. So this is a genuinely missing stage, not a mis-scoped
existing one — a rename would not have fixed it.

Nothing here skips or calls a model: the preset is data, and the failure path
is exercised through the tool directly.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.llm import LLMConfig
from fichero_server.models import DocType, Document
from fichero_server.workflows.preset_manifest import (
    check_preset_manifest,
    load_manifest,
    load_shipped_presets,
)
from fichero_server.workflows.tools.catalogue import catalogue
from fichero_server.workflows.validation import validate_node_connections
from fichero_server.workflows.types import EdgeDef, NodeDef, WorkflowDef

PRESET = (
    Path(__file__).parents[3]
    / "src"
    / "fichero_server"
    / "resources"
    / "default_workflows"
    / "catalogue_stage_6_catalogue.json"
)


def _preset() -> dict:
    return json.loads(PRESET.read_text(encoding="utf-8"))


class TestTheStageExistsAndIsNamedInTheSeries:
    def test_preset_ships(self):
        assert PRESET.exists(), "6 · Catalogue is not shipped"

    def test_it_is_named_in_the_same_series_as_its_siblings(self):
        """The vocabulary fix: `1 ·` … `6 ·` are the stages, `Catalogue` is
        the composite. One word naming both is why asking for one gave the
        other."""
        assert _preset()["name"] == "6 · Catalogue"

    def test_it_runs_the_catalogue_tool_and_not_the_earlier_stages(self):
        """The entire point: it must NOT re-transcribe or re-extract, or a
        user's corrections are overwritten by the run meant to describe them.
        """
        tools = {node["tool"] for node in _preset()["nodes"]}
        assert "catalogue" in tools
        forbidden = {
            "transcribe",
            "extract_all",
            "extract_entities_only",
            "extract_svo_only",
            "merge_dedup_only",
            "kg_persist_finalize",
            "import_artifacts",
        }
        assert not (tools & forbidden), (
            f"stage 6 would re-run earlier stages: {sorted(tools & forbidden)}"
        )

    def test_the_stage_series_is_now_complete(self):
        """1..6 all present, so the composite can later be expressed as a
        chain of them rather than 12 anonymous duplicated nodes (#4415)."""
        directory = PRESET.parent
        names = {
            json.loads(p.read_text(encoding="utf-8"))["name"]
            for p in directory.glob("catalogue_stage_*.json")
        }
        assert {name.split(" ·")[0] for name in names} == {
            "1", "2", "3", "4", "5", "6",
        }


class TestThePresetIsValid:
    def test_every_node_validates(self):
        """A required input port left unwired is a validation error, so this
        is what proves the preset is actually runnable rather than merely
        well-formed JSON."""
        preset = _preset()
        for node in preset["nodes"]:
            fed_by_edges = {
                edge["target_port"]
                for edge in preset["edges"]
                if edge["target"] == node["id"]
            }
            errors = validate_node_connections(
                NodeDef(
                    id=node["id"],
                    tool=node["tool"],
                    label=node.get("label"),
                    config=node.get("config", {}),
                ),
                edge_target_ports=fed_by_edges,
            )
            assert errors == [], f"{node['id']}: {errors}"

    def test_it_builds_as_a_workflow(self):
        preset = _preset()
        workflow = WorkflowDef(
            name=preset["name"],
            nodes=[NodeDef(**node) for node in preset["nodes"]],
            edges=[EdgeDef(**edge) for edge in preset["edges"]],
        )
        assert len(workflow.nodes) == 2

    def test_it_is_recorded_in_the_preset_manifest(self):
        """New presets must be recorded or the guardrail reports a violation."""
        violations = check_preset_manifest(load_shipped_presets(), load_manifest())
        assert violations == [], violations


class TestAbsentPrerequisitesFailLoudlyAndNameTheStage:
    """The failure mode this preset is most likely to hit, and the one that
    would be worst if silent: run stage 6 on material stages 2-4 never
    touched, and get a confident empty description."""

    @pytest.fixture
    def library(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
        package = tmp_path / "stage6.fichero"
        seed(package)
        db = db_manager.get_database(package)
        folder = Document(id="s6-folder", name="Caja 3", doc_type=DocType.folder)
        db.save(folder)
        return package, folder.id

    def test_no_claims_and_no_text_reports_what_is_missing(self, library):
        package, folder_id = library
        result = asyncio.run(
            catalogue(
                inputs={},
                state={
                    "library_path": str(package),
                    "selected_doc_ids": [folder_id],
                    "task_id": "stage6-run",
                },
                llm_config=LLMConfig(provider="$small", model="$small"),
            )
        )

        error = result.get("error") or ""
        assert error, (
            "a catalogue run with nothing to describe reported success — the "
            "#4283 shape, on the stage most likely to hit it"
        )
        assert "Caja 3" in error, "the error must name WHAT could not be described"
        assert "2 · Extract Entities" in error, (
            "the error must name WHICH STAGE produces the missing input — "
            "otherwise the user is told an input is missing with no way to "
            "know how to supply it"
        )
        assert result["text"] == ""

    def test_the_old_message_no_longer_misdirects(self, library):
        """It used to say 'No aggregated text provided', sending the user to
        look for a wiring fault. Stage 6 does not take text — it reads the
        claims stages 2-4 wrote."""
        package, folder_id = library
        result = asyncio.run(
            catalogue(
                inputs={},
                state={
                    "library_path": str(package),
                    "selected_doc_ids": [folder_id],
                    "task_id": "stage6-run",
                },
                llm_config=LLMConfig(provider="$small", model="$small"),
            )
        )
        assert "No aggregated text provided" not in (result.get("error") or "")
