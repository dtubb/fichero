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
        from fichero_server.api.routes.workflows import _tool_to_response

        td = get_tool_def("transcribe")
        resp = _tool_to_response(td)
        assert resp.tested is True

        td2 = get_tool_def("describe")  # a non-HTR builtin
        assert _tool_to_response(td2).tested is False

    def test_tool_response_field_present(self):
        from fichero_server.api.routes.workflows import ToolResponse

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

    def test_only_htr_preset_is_tested(self):
        tested = {
            p.name
            for p in self._preset_files()
            if self._is_tested(json.loads(p.read_text()))
        }
        assert tested == {_HTR_PRESET}, (
            f"exactly the HTR preset must carry config.tested=true; got {tested}"
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
        from fichero_server.api.routes.workflows import _workflow_untested

        return _workflow_untested(SimpleNamespace(is_system=is_system, config=config))

    def test_system_preset_without_flag_is_untested(self):
        assert self._untested(is_system=True, config={"preset_version": 2}) is True

    def test_system_preset_with_tested_flag_is_trusted(self):
        assert self._untested(is_system=True, config={"tested": True}) is False

    def test_user_workflow_never_untested(self):
        # is_system=False → never flagged, even with no config.
        assert self._untested(is_system=False, config={}) is False
        assert self._untested(is_system=False, config=None) is False
