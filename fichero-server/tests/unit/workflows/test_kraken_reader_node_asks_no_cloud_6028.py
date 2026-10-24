"""#6028: 'Read the lines with Kraken' calls no model, so preflight must not resolve it to the app's default vision model
(a cloud one) and refuse it with a cloud error on a project that keeps its pages here."""

from types import SimpleNamespace

from fichero_server.workflows.types import NodeDef, WorkflowDef
from fichero_server.workflows.validation import validate_workflow_llm_preflight


def _db():
    return SimpleNamespace(
        get_setting=lambda key: None,
        get_default_model_for_category=lambda category: ("openrouter", "google/gemini-2.5-flash"),
        list_providers=lambda: [],
        list_models=lambda provider_id: [],
    )


def _errors(monkeypatch, config):
    monkeypatch.setattr("fichero_server.db.app.get_app_db", _db)
    node = NodeDef(id="kraken-htr", tool="transcribe", label="Read the lines with Kraken", config=config)
    return validate_workflow_llm_preflight(WorkflowDef(id="wf", name="W", nodes=[node], edges=[]))


def test_a_kraken_reader_node_is_not_given_the_apps_cloud_default(monkeypatch):
    assert _errors(monkeypatch, {"vision_mode": "kraken", "kraken_model": "kraken-mccatmus"}) == []


def test_a_node_that_reads_with_a_model_still_resolves_the_default(monkeypatch):
    errors = _errors(monkeypatch, {"vision_mode": "kraken", "kraken_model": ""})
    assert errors, "no Kraken reader named: the vision model reads, so the model rules apply"


def test_no_vision_mode_means_auto_so_the_model_rules_still_apply(monkeypatch):
    errors = _errors(monkeypatch, {"kraken_model": "kraken-mccatmus"})
    assert errors, "transcribe's default mode is auto: only an explicit 'kraken' skips the check"
