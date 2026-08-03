"""What will this workflow ACTUALLY call, and will it cost money (#4503).

A preset declares a tier; the app database decides the provider. Nothing in the
preset records which one you get, so "is this free?" is a property of preset
PLUS database. That cost real money twice on 2026-08-03 — a probe expected to
be on-device that went to OpenRouter, and a triage that classified presets as
free by reading their JSON. Neither was careless; the answer was not in the
file either was reading.

The last test in TestTheCaseThatCostMoney is the one that matters: a preset
whose JSON says nothing about providers, reported as PAID, because the database
says so.

Nothing here makes a network call. A cost preview that costs money would be
self-defeating, and one test asserts exactly that.
"""

from __future__ import annotations

import pytest

from fichero_server.workflows.provider_preview import (
    ResolutionSource,
    preview_preset_providers,
    preview_workflow_providers,
)
from fichero_server.models import Workflow
from fichero_server.workflows.runtime import to_workflow_def

import fichero_server.workflows.tools  # noqa: F401


def _wf(nodes, *, name="probe", config=None):
    return to_workflow_def(
        Workflow(
            id="probe", name=name, nodes=nodes, edges=[],
            config=config or {}, folder_path="/",
        )
    )


def _node(node_id, tool, **cfg):
    return {"id": node_id, "tool": tool, "config": cfg, "inputs": {}, "label": node_id}


class _FakeAppDB:
    """The app database, which is what actually decides.

    Env vars are NOT enough to control this. Writing these tests surfaced a
    second gap worth stating: `FICHERO_<TIER>_PROVIDER` only reaches
    `resolve_model_alias`, i.e. nodes that name a `$tier`. A node with NO
    provider skips aliases entirely and goes to
    `app_db.get_default_model_for_category(...)`, which reads the database and
    never looks at the environment.

    So env pinning does not protect the majority case. Any fail-closed guard
    built on env alone is incomplete — which is precisely the kind of
    almost-right safety measure this whole issue is about.
    """

    def __init__(self, provider: str, model: str):
        self._provider = provider
        self._model = model

    def get_setting(self, key: str):
        if key.endswith("_provider"):
            return self._provider
        if key.endswith("_model"):
            return self._model
        return None

    def get_default_model_for_category(self, category):
        return (self._provider, self._model)

    def get_default_model(self):
        return (self._provider, self._model)

    def list_providers(self):
        return []

    def list_models(self, _provider_id):
        return []


def _use_app_db(monkeypatch, provider: str, model: str):
    fake = _FakeAppDB(provider, model)
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: fake)
    # Clear env so the alias path also falls through to this database rather
    # than to a stray pin left by another test or the developer's shell.
    for tier in ("VISION", "VISION_SMALL", "VISION_MEDIUM", "VISION_LARGE",
                 "TEXT", "SMALL", "MEDIUM", "LARGE"):
        monkeypatch.delenv(f"FICHERO_{tier}_PROVIDER", raising=False)
        monkeypatch.delenv(f"FICHERO_{tier}_MODEL", raising=False)
    return fake


@pytest.fixture
def on_device_db(monkeypatch):
    """A factory install: FACTORY_AI_DEFAULTS is fully on-device since #4325."""
    return _use_app_db(monkeypatch, "apple", "apple-vision")


@pytest.fixture
def paid_db(monkeypatch):
    """The configuration this machine was actually in when it billed."""
    return _use_app_db(monkeypatch, "openrouter", "google/gemini-3-flash-preview")


class TestANodeThatCallsNoModelIsFreeUnderAnyConfiguration:
    """The only thing in this system honestly callable free from the file alone."""

    def test_a_deterministic_tool_reports_no_model(self, paid_db):
        preview = preview_workflow_providers(_wf([_node("split", "split_images")]))
        node = preview.nodes[0]
        assert node.uses_model is False
        assert node.source is ResolutionSource.none
        assert node.billable is None

    def test_such_a_workflow_is_free_even_on_a_paid_database(self, paid_db):
        """Group A's whole claim. If this ever fails, 'free-deterministic' is
        no longer a category and the #4501 labels are wrong."""
        preview = preview_workflow_providers(
            _wf([_node("a", "split_images"), _node("b", "rotate_images")])
        )
        assert preview.is_free
        assert not preview.would_cost_money


class TestTheSourceIsReportedNotJustTheAnswer:
    """'openrouter, pinned on the node' and 'openrouter, from the database' are
    different facts. Only the second is a surprise, and only the second is
    invisible to someone reading the preset."""

    def test_a_node_pinned_provider_is_reported_as_coming_from_the_node(self, on_device_db):
        preview = preview_workflow_providers(
            _wf([_node("t", "transcribe", provider_name="openrouter",
                       model_name="google/gemini-3-flash-preview")])
        )
        node = preview.nodes[0]
        assert node.source is ResolutionSource.node
        assert node.billable is True
        assert node.is_surprise is False, (
            "a provider written in the preset is not a surprise — flagging it "
            "as one would bury the invisible case in noise"
        )

    def test_a_node_pinned_provider_beats_the_database(self, on_device_db):
        """Precedence, asserted against a database that says otherwise."""
        preview = preview_workflow_providers(
            _wf([_node("t", "transcribe", provider_name="openrouter",
                       model_name="google/gemini-3-flash-preview")])
        )
        assert preview.nodes[0].provider == "openrouter"

    def test_an_unpinned_node_is_reported_as_coming_from_the_database(self, paid_db):
        preview = preview_workflow_providers(_wf([_node("t", "transcribe")]))
        node = preview.nodes[0]
        assert node.source in {ResolutionSource.app_db, ResolutionSource.env}
        assert node.provider == "openrouter"


class TestOnDeviceIsReportedFree:
    def test_an_apple_provider_is_not_billable(self, on_device_db):
        preview = preview_workflow_providers(_wf([_node("t", "transcribe")]))
        node = preview.nodes[0]
        assert node.provider == "apple"
        assert node.billable is False
        assert preview.is_free

    def test_an_unknown_provider_is_treated_as_billable(self, monkeypatch):
        """If we cannot establish that something is on-device, 'free' is the
        expensive guess. Fail toward the safe answer."""
        from fichero_server.workflows import provider_preview

        assert provider_preview._provider_is_billable("not-a-real-provider") is True


class TestTheCaseThatCostMoney:
    """A preset whose JSON says nothing about providers, reported PAID."""

    def test_an_unpinned_preset_is_reported_paid_when_the_database_is_paid(self, paid_db):
        preview = preview_workflow_providers(_wf([_node("t", "transcribe")]))
        assert preview.would_cost_money is True
        assert not preview.is_free

    def test_and_it_is_flagged_as_a_SURPRISE(self, paid_db):
        """The exact shape that cost money twice: nothing in the file says
        paid, and the run bills anyway. This is the assertion whose failure
        means the class is back."""
        preview = preview_workflow_providers(_wf([_node("t", "transcribe")]))
        assert preview.surprises, (
            "a preset that bills while its JSON says nothing about providers "
            "must be flagged as a surprise — that invisibility IS the defect"
        )

    def test_the_same_preset_is_free_on_a_factory_database(self, on_device_db):
        """Proves the verdict tracks the DATABASE, not the file. Same preset,
        opposite answer — which is the whole finding."""
        preview = preview_workflow_providers(_wf([_node("t", "transcribe")]))
        assert preview.is_free is True

    def test_a_real_shipped_preset_is_reported_paid_on_a_paid_database(self, paid_db):
        """Not a synthetic node — a preset actually shipped in the app, of the
        kind that was swept as 'free via Apple Vision' and billed."""
        from fichero_server.workflows.default_workflows import _load_preset_files

        preset = next(p for p in _load_preset_files() if p["name"] == "Transcribe")
        preview = preview_preset_providers(preset)
        assert preview.would_cost_money is True
        assert preview.surprises


class TestUnresolvableIsNotFree:
    def test_an_unresolvable_node_is_reported_not_silently_free(self, monkeypatch):
        """Reporting unknown as free is how this class recurs."""
        for tier in ("VISION", "VISION_SMALL", "VISION_MEDIUM", "VISION_LARGE",
                     "TEXT", "SMALL", "MEDIUM", "LARGE"):
            monkeypatch.delenv(f"FICHERO_{tier}_PROVIDER", raising=False)
            monkeypatch.delenv(f"FICHERO_{tier}_MODEL", raising=False)

        def _boom(*a, **k):
            raise ValueError("no Default Vision model is configured")

        monkeypatch.setattr(
            "fichero_server.workflows.builder._resolve_node_llm_config_inner", _boom
        )
        preview = preview_workflow_providers(_wf([_node("t", "transcribe")]))
        node = preview.nodes[0]
        assert node.source is ResolutionSource.unresolved
        assert node.error and "Default Vision" in node.error
        assert preview.is_free is False, (
            "an unresolvable node is UNKNOWN, not free; calling it free is the "
            "same guess that cost money"
        )


class TestThePreviewMakesNoCall:
    def test_previewing_every_shipped_preset_contacts_nothing(self, paid_db, monkeypatch):
        """The preview must be safe to run against a paid configuration — that
        is its entire purpose. If it ever calls out, using it to check before
        spending would itself spend."""
        import fichero_server.llm as llm_mod

        called: list[str] = []

        async def _forbidden(*a, **k):
            called.append("chat")
            raise AssertionError("the preview made a model call")

        monkeypatch.setattr(llm_mod, "chat_with_fallback", _forbidden, raising=False)
        monkeypatch.setattr(llm_mod, "chat", _forbidden, raising=False)

        from fichero_server.workflows.default_workflows import _load_preset_files

        for preset in _load_preset_files():
            preview_preset_providers(preset)
        assert called == []


class TestConfigurationIndependentPresetsCallNoModel:
    """The guardrail that would have caught my own mistake (#4501/#4503).

    "Group Same Documents" was classified free-deterministic and marked
    config.tested, on the strength of grepping its tools for
    `chat_with_fallback` / `apple_vision_ocr` and finding none. But
    `similarity` reaches a provider through `await vision(...)`, which that
    grep did not look for — so a preset labelled validated-under-any-
    configuration in fact billed on a paid database, and its own validation run
    made a paid call. A name/pattern scan cannot answer this. `ToolDef.uses_llm`
    is the tool's own declaration and is what the RUNNER consults, so it is what
    this checks.

    Scoped to the configuration-independent set on purpose. "Validated" and
    "free" are NOT the same claim: a preset can legitimately be validated
    against a paid provider. What it cannot do is claim a
    configuration-independent label while containing a node whose provider the
    app database decides.
    """

    #: The #4501 phase-1 set: validated by running them, and free under ANY
    #: configuration because no node resolves a provider at all.
    CONFIGURATION_INDEPENDENT = {
        "1 \u00b7 Import \u2192 Artifacts", "4 \u00b7 Merge / Dedup",
        "5 \u00b7 KG Persist / Finalize", "Enhance Images",
        "Export to Desktop (MD + DOCX + XLSX)", "Fuzzy Clean Images",
        "Prepare Images for OCR", "Recombine Segments",
        "Remove Background Images", "Rotate / Auto-Orient Images",
        "Segment Images", "Split Chapters", "Split Images",
    }

    def test_none_of_them_resolves_a_provider(self, paid_db):
        from fichero_server.workflows.default_workflows import _load_preset_files

        offenders = {}
        for preset in _load_preset_files():
            if preset["name"] not in self.CONFIGURATION_INDEPENDENT:
                continue
            preview = preview_preset_providers(preset)
            model_nodes = sorted({n.tool for n in preview.nodes if n.uses_model})
            if model_nodes:
                offenders[preset["name"]] = model_nodes

        assert not offenders, (
            "these presets are labelled free under any configuration but "
            f"contain nodes that resolve a provider: {offenders}. A 'tested' "
            "label that depends on the reader's app database is the wallpaper "
            "problem with the sign flipped"
        )

    def test_they_are_free_on_a_paid_database(self, paid_db):
        """The claim itself, end to end: paid DB, still free."""
        from fichero_server.workflows.default_workflows import _load_preset_files

        for preset in _load_preset_files():
            if preset["name"] not in self.CONFIGURATION_INDEPENDENT:
                continue
            assert preview_preset_providers(preset).is_free, preset["name"]


class TestTheOneLegacyTestedPresetIsConfigurationDependent:
    """Recording a fact rather than failing on it (#4501).

    `Transcribe HTR` carried config.tested long before this work, and it is NOT
    configuration-independent: its transcribe / transcribe_review nodes resolve
    a provider from the app database like any other. That is not necessarily
    wrong — it was presumably validated against some real provider — but the
    label does not record WHICH, so a user on a paid database sees "validated"
    on a preset that will bill them.

    This is the concrete instance of the rule written into
    agent-work/status/2026-08-03-preset-triage.md: a removed (Untested) label
    must state the configuration it was earned under. Pinned here so the gap is
    visible and dated rather than rediscovered.
    """

    def test_htr_resolves_a_provider_from_the_database(self, paid_db):
        from fichero_server.workflows.default_workflows import _load_preset_files

        preset = next(
            p for p in _load_preset_files() if p["name"] == "Transcribe HTR"
        )
        preview = preview_preset_providers(preset)
        assert (preset.get("config") or {}).get("tested") is True
        assert preview.would_cost_money, (
            "if HTR has become configuration-independent, this recorded gap is "
            "closed — delete this test and say so"
        )


class TestDelegationIsNotSilentlyFree:
    """A preset whose cost lives in a child (#4503).

    "Transcribe Spanish Script (19th-20th C.)" runs `sub_workflow` and nothing
    else that resolves a provider. Read naively it has zero model nodes, so the
    first version of this preview called it free under any configuration — a
    confident wrong answer about a preset that delegates its entire cost.

    That is this module's own defect class reproduced one level down: the
    answer is real, and it is somewhere the reader is not looking. Until
    delegation is followed, the honest answer is UNKNOWN, and unknown is not
    free.
    """

    def test_a_delegating_preset_is_not_reported_free(self, on_device_db):
        from fichero_server.workflows.default_workflows import _load_preset_files

        preset = next(
            p for p in _load_preset_files()
            if p["name"] == "Transcribe Spanish Script (19th-20th C.)"
        )
        preview = preview_preset_providers(preset)
        assert not preview.is_free, (
            "a preset that delegates its work was reported free — its cost is "
            "in the child workflow, which this preview does not follow"
        )
        assert preview.unresolved_nodes
        assert "delegat" in (preview.unresolved_nodes[0].error or "")

    def test_a_sub_workflow_node_says_why_it_is_unknown(self, on_device_db):
        """An unexplained 'unresolved' would just move the confusion."""
        preview = preview_workflow_providers(_wf([_node("child", "sub_workflow")]))
        node = preview.nodes[0]
        assert node.source is ResolutionSource.unresolved
        assert "does not follow delegation" in (node.error or "")
