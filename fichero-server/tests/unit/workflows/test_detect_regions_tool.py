"""detect_regions: the bboxes-first pre-pass (Daniel, 2026-08-11).

The tool must be registered, fan out per file, FORCE the local Apple
provider (a cloud workflow's llm_config must not leak in), persist under
artifact_type "regions", and pass files/documents through untouched so a
transcriber chains directly after it.
"""

import json
from pathlib import Path

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.builder import PARALLEL_TOOLS
from fichero_server.workflows.registry import get_tool, get_tool_def
from fichero_server.workflows.tools import detect_regions as detect_regions_module


class TestRegistration:
    def test_registered_and_parallel(self):
        assert get_tool("detect_regions") is not None
        assert "detect_regions" in PARALLEL_TOOLS

    def test_marked_local_only(self):
        tool_def = get_tool_def("detect_regions")
        assert tool_def is not None
        assert tool_def.uses_llm is False

    def test_artifact_type_is_regions(self):
        assert detect_regions_module.TOOL_CONFIG.artifact_type == "regions"
        # Regions never overwrite a page's text or spend embedding work.
        assert detect_regions_module.TOOL_CONFIG.update_page_content is False
        assert detect_regions_module.TOOL_CONFIG.trigger_embedding is False


class TestRun:
    @pytest.mark.asyncio
    async def test_forces_apple_provider_and_passes_files_through(
        self, monkeypatch
    ):
        captured: dict = {}

        async def fake_process_vision(**kwargs):
            captured.update(kwargs)
            return {"results": [{"file": "/a.jpg"}], "success_count": 1}

        monkeypatch.setattr(
            detect_regions_module, "process_vision", fake_process_vision
        )

        cloud_config = LLMConfig(provider="google", model="gemini-2.5-pro")
        result = await detect_regions_module.detect_regions(
            inputs={"files": ["/a.jpg", "/b.jpg"], "documents": [{"id": "d1"}]},
            state={"library_path": "/lib", "task_id": "t1"},
            llm_config=cloud_config,
        )

        forced = captured["llm_config"]
        assert forced.provider == "apple"
        assert captured["vision_mode"] == "apple"
        assert captured["tool_config"].artifact_type == "regions"
        # Passthrough: a transcriber chained after this node sees the same
        # inputs the source produced.
        assert result["files"] == ["/a.jpg", "/b.jpg"]
        assert result["documents"] == [{"id": "d1"}]


class TestTranscribeIntegration:
    """Bboxes-first inside transcribe: detection runs BEFORE the vision call,
    is on by default, off by config, and never costs a transcription."""

    @pytest.fixture
    def call_order(self, monkeypatch):
        from fichero_server.workflows.tools import transcribe as transcribe_module

        order: list[str] = []

        async def fake_detect(**kwargs):
            order.append("detect")
            return {"results": []}

        async def fake_process_vision(**kwargs):
            order.append("transcribe")
            return {"results": [], "success_count": 0}

        monkeypatch.setattr(
            detect_regions_module, "detect_regions", fake_detect
        )
        monkeypatch.setattr(
            transcribe_module, "process_vision", fake_process_vision
        )
        return order

    async def _run_transcribe(self, inputs):
        from fichero_server.workflows.tools.transcribe import transcribe

        return await transcribe(
            inputs=inputs,
            state={"library_path": "/lib", "input_files": []},
            llm_config=LLMConfig(provider="google", model="gemini-2.5-pro"),
        )

    @pytest.mark.asyncio
    async def test_detection_runs_before_transcription_by_default(
        self, call_order
    ):
        await self._run_transcribe({"files": ["/a.jpg"], "documents": []})
        assert call_order == ["detect", "transcribe"]

    @pytest.mark.asyncio
    async def test_regions_first_false_skips_detection(self, call_order):
        await self._run_transcribe(
            {"files": ["/a.jpg"], "documents": [], "regions_first": False}
        )
        assert call_order == ["transcribe"]

    @pytest.mark.asyncio
    async def test_detection_failure_never_costs_the_transcription(
        self, call_order, monkeypatch
    ):
        async def exploding_detect(**kwargs):
            raise RuntimeError("Vision framework unavailable")

        monkeypatch.setattr(
            detect_regions_module, "detect_regions", exploding_detect
        )
        await self._run_transcribe({"files": ["/a.jpg"], "documents": []})
        assert call_order == ["transcribe"]


class TestPreset:
    def test_detect_regions_preset_parses_and_resolves(self):
        preset_path = (
            Path(detect_regions_module.__file__).resolve().parents[2]
            / "resources"
            / "default_workflows"
            / "detect_regions.json"
        )
        data = json.loads(preset_path.read_text())
        assert data["name"] == "Detect Regions"
        for node in data["nodes"]:
            assert get_tool(node["tool"]) is not None, (
                f"preset node tool {node['tool']!r} does not resolve"
            )
        node_ids = {n["id"] for n in data["nodes"]}
        for edge in data["edges"]:
            assert edge["source"] in node_ids and edge["target"] in node_ids
