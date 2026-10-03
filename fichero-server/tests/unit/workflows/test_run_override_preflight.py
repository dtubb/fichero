"""A run's model choice is what preflight checks, and a new workflow follows the library's defaults (#5402).

Found on the Sergio engine (2026-10-03): `workflow create` with no provider stored the workflow as
`openai / gpt-4o` (WorkflowDef's class default) in a library whose AI defaults are all OpenRouter and
which has no OpenAI key; then `workflow run ... --model openrouter/google/gemini-3-flash-preview` was
refused, "Provider 'OpenAI' requires an API key", because preflight checked the stored provider,
not the model the run would use.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from fichero_server.api.routes.workflow.workflows import create_workflow_impl
from fichero_server.api.routes.workflow_execution.core import _validate_workflow_for_execution
from fichero_server.models import Workflow
from fichero_server.workflows.types import WorkflowDef

PRESETS = Path(__file__).resolve().parents[3] / "src" / "fichero_server" / "resources" / "default_workflows"


@pytest.fixture
def only_an_openrouter_key(monkeypatch):
    """The Sergio library: an OpenRouter key, no OpenAI key."""
    monkeypatch.setattr("fichero_server.llm.get_api_key",
                        lambda provider: "sk-or-test" if str(provider).lower() == "openrouter" else None)


def _transcribe_stored_as_openai() -> Workflow:
    preset = json.loads((PRESETS / "transcribe_manuscript.json").read_text())
    return Workflow(id="wf-5402", name="Transcribe (stored as openai)", format="nodes",
                    provider="openai", model="gpt-4o", nodes=preset["nodes"], edges=preset["edges"])


def test_a_run_with_a_model_is_checked_against_that_model(only_an_openrouter_key):
    """WHY: the run's choice is what the nodes will call. Refusing it for a key the run will never
    use blocks every run of a workflow created with the class default, whatever model is asked for."""
    request = SimpleNamespace(provider_override="openrouter", model_override="google/gemini-3-flash-preview")
    stored = _transcribe_stored_as_openai()
    nodes_before = json.dumps(stored.nodes, sort_keys=True)
    assert _validate_workflow_for_execution(stored, request, None) is None
    # The choice is checked on a copy: the stored workflow is not rewritten by a preflight.
    assert stored.provider == "openai" and json.dumps(stored.nodes, sort_keys=True) == nodes_before


def test_without_a_choice_the_stored_provider_is_still_checked(only_an_openrouter_key):
    """WHY: the fix must not switch the check off. A run with no choice really will call the stored
    provider, so a missing key for it is still refused before the run starts."""
    with pytest.raises(HTTPException) as refused:
        _validate_workflow_for_execution(_transcribe_stored_as_openai(), SimpleNamespace(), None)
    assert "requires an API key" in refused.value.detail


def test_a_new_workflow_that_names_no_model_follows_the_library_defaults(db):
    """WHY: a workflow stored as `openai / gpt-4o` because the caller named nothing cannot run in a
    library without an OpenAI key, and ignores the defaults the person set. Stored empty, each node
    resolves the library's AI defaults (its vision or text slot) when it runs."""
    stored = create_workflow_impl(db, WorkflowDef(name="No model named", nodes=[], edges=[]))
    assert (stored.provider, stored.model) == ("", "")


def test_a_named_model_is_kept(db):
    """WHY: a caller who does name a provider and model (the app's editor, `--provider/--model`) must
    get exactly that; only an unnamed one follows the defaults."""
    stored = create_workflow_impl(db, WorkflowDef(name="Named", provider="openrouter",
                                                  model="google/gemini-3-flash-preview"))
    assert (stored.provider, stored.model) == ("openrouter", "google/gemini-3-flash-preview")
