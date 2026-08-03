"""
Untested-flag tests.

Directive: mark everything UNTESTED except the HTR transcription
chain, so users can see what is trustworthy.

Two surfaces are covered:
  * the per-tool `tested` flag on ToolDef / register_tool / the registry API, and
  * the workflow PRESET names, which carry a "(Untested)" suffix everywhere
    except the HTR preset.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fichero_server.workflows.registry import (
    register_tool,
    get_tool_def,
    list_tools,
)
from fichero_server.workflows.types import ToolDef

# The four tools the HTR two-pass preset (transcribe_htr.json) is built from.
HTR_TOOLS = {"files", "transcribe", "transcribe_review", "search"}

_PRESETS_DIR = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "fichero_server"
    / "resources"
    / "default_workflows"
)
_HTR_PRESET = "transcribe_htr.json"

#: The deterministic presets validated by #4501 phase 1 (2026-08-03): each run
#: through the real graph, with its terminal node checked to have produced what
#: the preset claims — not merely that the run exited 0. They call no model at
#: all, which is what makes them free to validate under ANY configuration.
_GROUP_A_VALIDATED_FILES = {
    "catalogue_stage_1_import_artifacts.json",
    "catalogue_stage_4_merge_dedup.json",
    "catalogue_stage_5_kg_persist.json",
    "enhance_images.json",
    "export_to_desktop.json",
    "fuzzy_clean_images.json",
    "group_same_documents.json",
    "prepare_images_for_ocr.json",
    "recombine_segments.json",
    "remove_background_images.json",
    "rotate_auto_orient_images.json",
    "segment_images.json",
    "split_chapters.json",
    "split_images.json",
}


class TestToolTestedFlag:
    """The `tested` flag defaults to False and only the HTR chain is True."""

    def test_tooldef_defaults_untested(self):
        """A bare ToolDef is UNTESTED unless explicitly marked."""
        td = ToolDef(name="x", display_name="X")
        assert td.tested is False

    def test_register_tool_defaults_untested(self):
        """@register_tool without tested= registers an UNTESTED tool."""

        @register_tool(
            name="_untested_probe_tool",
            display_name="Untested Probe",
            description="probe",
            category="test",
        )
        async def _probe(state, config):  # pragma: no cover - never executed
            return {}

        td = get_tool_def("_untested_probe_tool")
        assert td is not None
        assert td.tested is False

    def test_register_tool_can_mark_tested(self):
        """@register_tool(tested=True) flows through to the ToolDef."""

        @register_tool(
            name="_tested_probe_tool",
            display_name="Tested Probe",
            description="probe",
            category="test",
            tested=True,
        )
        async def _probe(state, config):  # pragma: no cover - never executed
            return {}

        td = get_tool_def("_tested_probe_tool")
        assert td is not None
        assert td.tested is True

    def test_only_htr_tools_are_tested(self):
        """Across the whole live registry, exactly the HTR chain is tested.

        Underscore-prefixed names are ignored: those are probe tools other
        unit tests inject into the shared global registry.
        """
        tested = {
            t.name for t in list_tools() if t.tested and not t.name.startswith("_")
        }
        assert tested == HTR_TOOLS, (
            f"Expected only {HTR_TOOLS} tested, got {tested}"
        )

    @pytest.mark.parametrize("name", sorted(HTR_TOOLS))
    def test_htr_tool_marked_tested(self, name):
        td = get_tool_def(name)
        assert td is not None, f"{name} not registered"
        assert td.tested is True


class TestToolRegistryApiExposesTested:
    """The registry API response model carries the `tested` field."""

    def test_tool_response_serializes_tested(self):
        from fichero_server.api.routes.workflow.workflows import _tool_to_response

        td = get_tool_def("transcribe")
        resp = _tool_to_response(td)
        assert resp.tested is True

        td2 = get_tool_def("describe")  # a non-HTR builtin
        assert _tool_to_response(td2).tested is False

    def test_tool_response_field_present(self):
        from fichero_server.api.routes.workflow.workflows import ToolResponse

        assert "tested" in ToolResponse.model_fields


class TestPresetUntestedFlag:
    """Exactly one shipped preset (the HTR chain) opts into `config.tested`;
    every other preset is therefore untested. Preset NAMES stay stable — the
    "(Untested)" suffix is a display concern applied by the UI from the flag,
    never baked into the canonical name (that broke every name-keyed lookup)."""

    def _preset_files(self):
        return sorted(_PRESETS_DIR.glob("*.json"))

    def _is_tested(self, data) -> bool:
        return bool((data.get("config") or {}).get("tested", False))

    def test_presets_exist(self):
        assert len(self._preset_files()) > 1

    def test_every_preset_parses(self):
        parsed = [json.loads(p.read_text()) for p in self._preset_files()]
        assert len(parsed) == len(self._preset_files())

    def test_only_deliberately_validated_presets_are_tested(self):
        """The tested set is an explicit allowlist, not a floor.

        Was `== {_HTR_PRESET}` — correct while HTR was the only validated
        preset, obsolete once #4501 phase 1 validated the 14 deterministic
        ones. Widened by ENUMERATION rather than relaxed to `>=`: the point of
        this assertion is that a preset cannot acquire `config.tested` without
        someone editing this list, which a floor would allow silently. Adding a
        name here is the deliberate act of claiming it was validated.
        """
        tested = {
            p.name
            for p in self._preset_files()
            if self._is_tested(json.loads(p.read_text()))
        }
        expected = {_HTR_PRESET} | _GROUP_A_VALIDATED_FILES
        assert tested == expected, (
            "config.tested must match the validated allowlist exactly. "
            f"unexpected={sorted(tested - expected)} "
            f"missing={sorted(expected - tested)}"
        )

    def test_htr_preset_name_and_flag(self):
        data = json.loads((_PRESETS_DIR / _HTR_PRESET).read_text())
        assert data["name"] == "Transcribe HTR"  # name stays stable
        assert self._is_tested(data)

    def test_no_preset_name_carries_untested_suffix(self):
        """Regression guard: the trust label must NOT leak into the canonical
        name — it is the identity/lookup key and the prior name-suffix approach
        broke ~13 name-keyed tests + any chat/CLI run-by-name."""
        for p in self._preset_files():
            name = json.loads(p.read_text()).get("name", "")
            assert "(Untested)" not in name, (
                f"{p.name} name {name!r} must not bake in the trust label"
            )


class TestWorkflowUntestedResponse:
    """The API derives `untested` from is_system + config.tested."""

    def _untested(self, *, is_system, config):
        from fichero_server.api.routes.workflow.workflows import _workflow_untested

        return _workflow_untested(SimpleNamespace(is_system=is_system, config=config))

    def test_system_preset_without_flag_is_untested(self):
        assert self._untested(is_system=True, config={"preset_version": 2}) is True

    def test_system_preset_with_tested_flag_is_trusted(self):
        assert self._untested(is_system=True, config={"tested": True}) is False

    def test_user_workflow_never_untested(self):
        # is_system=False → never flagged, even with no config.
        assert self._untested(is_system=False, config={}) is False
        assert self._untested(is_system=False, config=None) is False


# =============================================================================
# #4501 phase 1 — the deterministic presets are validated, and stay that way
# =============================================================================


class TestGroupADeterministicPresetsAreTested:
    """The 14 presets that call NO model, validated 2026-08-03 by running each
    through the real graph and checking its terminal node actually produced
    what the preset claims to produce — not merely that the run exited 0.
    #4496 is why that distinction matters: it ran green end to end while
    storing the model's commentary as the transcription.

    These are the only presets that are free to validate under ANY
    configuration. Every other preset leaves provider/model unset on its
    model-using nodes, so what it costs depends on the user's app defaults —
    see agent-work/status/2026-08-03-preset-triage.md.
    """

    GROUP_A = {
        "1 · Import → Artifacts",
        "4 · Merge / Dedup",
        "5 · KG Persist / Finalize",
        "Enhance Images",
        "Export to Desktop (MD + DOCX + XLSX)",
        "Fuzzy Clean Images",
        "Group Same Documents",
        "Prepare Images for OCR",
        "Recombine Segments",
        "Remove Background Images",
        "Rotate / Auto-Orient Images",
        "Segment Images",
        "Split Chapters",
        "Split Images",
    }

    def _presets(self):
        from fichero_server.workflows.default_workflows import _load_preset_files

        return {p["name"]: p for p in _load_preset_files()}

    def test_every_validated_preset_carries_config_tested(self):
        presets = self._presets()
        missing = [
            name
            for name in sorted(self.GROUP_A)
            if not (presets.get(name, {}).get("config") or {}).get("tested")
        ]
        assert not missing, (
            f"these presets were validated but lost config.tested: {missing}. "
            "The UI derives '(Untested)' from that key, so dropping it puts the "
            "warning back on a preset that has been checked"
        )

    def test_no_group_a_preset_calls_a_model(self):
        """What makes this group free under ANY configuration. If a model-using
        tool is added to one, its cost silently becomes a function of the
        user's app defaults and the validation above no longer covers it."""
        model_tools = {
            "transcribe", "transcribe_review", "convert", "classify_script",
            "table_extract", "describe", "catalogue", "citations_extract",
            "clean_text", "extract_all", "extract_entities_only", "extract_geo",
            "extract_svo_only", "text_translate", "text_translate_review",
            "translate",
        }
        presets = self._presets()
        for name in sorted(self.GROUP_A):
            tools = {
                node.get("tool")
                for node in presets[name].get("nodes", [])
                if node.get("tool")
            }
            offending = tools & model_tools
            assert not offending, (
                f"{name!r} now uses {sorted(offending)}, which calls a model. "
                "It is no longer free under any configuration — re-triage it "
                "before leaving config.tested set"
            )

    def test_the_untested_label_is_no_longer_wallpaper(self):
        """The point of the exercise. 38 of 39 carrying the same warning meant
        the one preset that might deserve it got the same glance as the 37
        merely unchecked."""
        presets = self._presets()
        untested = [
            name
            for name, p in presets.items()
            if not (p.get("config") or {}).get("tested")
        ]
        assert len(untested) < len(presets) - 10, (
            f"{len(untested)} of {len(presets)} presets still carry (Untested); "
            "the label is still wallpaper"
        )
