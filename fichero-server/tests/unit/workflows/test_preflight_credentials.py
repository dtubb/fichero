"""#4325(b): preflight checks credential PRESENCE per resolved provider.

A missing API key must be a pre-run preflight message that names the provider,
never a node-construction crash mid-run. Local/built-in providers (apple,
mock, ollama, lmstudio, omlx) and unknown/custom provider names are never
gated.
"""

from __future__ import annotations

from types import SimpleNamespace

from fichero_server.llm import LLMConfig
from fichero_server.workflows.types import NodeDef, WorkflowDef
from fichero_server.workflows.validation import validate_workflow_llm_preflight


def _workflow_for(node: NodeDef) -> WorkflowDef:
    return WorkflowDef(id="wf", name="Workflow", nodes=[node], edges=[])


def _provider(provider_type: str):
    return SimpleNamespace(
        id=f"{provider_type}-provider",
        enabled=True,
        provider_type=SimpleNamespace(value=provider_type),
    )


def _model(model_id: str, capabilities: list[str]):
    return SimpleNamespace(model_id=model_id, capabilities=capabilities, enabled=True)


def _fake_db(models_by_provider=None):
    models_by_provider = models_by_provider or {}
    providers = [_provider(provider_type) for provider_type in models_by_provider]
    return SimpleNamespace(
        get_setting=lambda key: None,
        get_default_model_for_category=lambda category: None,
        list_providers=lambda: providers,
        list_models=lambda provider_id: models_by_provider.get(
            provider_id.removesuffix("-provider"), []
        ),
    )


def _common_env(monkeypatch, *, api_key):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    monkeypatch.setattr(
        "fichero_server.db.app.get_app_db",
        lambda: _fake_db(
            models_by_provider={
                "openai": [_model("gpt-5", ["text", "vision"])],
                "apple": [_model("apple-intelligence", ["text"])],
            }
        ),
    )
    monkeypatch.setattr("fichero_server.llm.get_api_key", lambda provider: api_key)


def test_missing_key_fails_preflight_naming_the_provider(monkeypatch):
    _common_env(monkeypatch, api_key=None)
    node = NodeDef(
        id="summarize",
        tool="summarize_file",
        provider_name="openai",
        model_name="gpt-5",
    )

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="", model="")
    )

    assert len(errors) == 1
    assert "OpenAI" in errors[0]
    assert "API key" in errors[0]
    assert "summarize" in errors[0]


def test_present_key_passes_preflight(monkeypatch):
    _common_env(monkeypatch, api_key="sk-test")
    node = NodeDef(
        id="summarize",
        tool="summarize_file",
        provider_name="openai",
        model_name="gpt-5",
    )

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="", model="")
    )

    assert errors == []


def test_on_device_provider_never_requires_a_key(monkeypatch):
    _common_env(monkeypatch, api_key=None)
    node = NodeDef(
        id="summarize",
        tool="summarize_file",
        provider_name="apple",
        model_name="apple-intelligence",
    )

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="", model="")
    )

    assert errors == []


def test_unknown_custom_provider_is_not_gated(monkeypatch):
    """Custom/off-catalog provider names (e.g. a self-hosted OpenAI-compatible
    endpoint) are not credential-gated — presence can't be known here."""
    _common_env(monkeypatch, api_key=None)
    monkeypatch.setattr(
        "fichero_server.llm.resolve_model_alias_for_capability",
        lambda provider, model, required_capability=None: (provider, model),
    )
    node = NodeDef(
        id="summarize",
        tool="summarize_file",
        provider_name="my-custom-endpoint",
        model_name="whatever",
    )

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="", model="")
    )

    assert errors == []


def test_keyless_fresh_install_passes_preflight_for_every_default_workflow(
    monkeypatch,
):
    """#4325 acceptance: zero API keys + factory AI defaults → every shipped
    default workflow passes LLM preflight (tier aliases resolve on-device)."""
    from fichero_server.db.app import FACTORY_AI_DEFAULTS
    from fichero_server.workflows.default_workflows import _load_preset_files
    from fichero_server.workflows.runtime import to_workflow_def
    from fichero_server.models import Workflow

    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    for tier in ("small", "medium", "large", "vision_small", "vision_medium", "vision_large"):
        monkeypatch.delenv(f"FICHERO_{tier.upper()}_PROVIDER", raising=False)
        monkeypatch.delenv(f"FICHERO_{tier.upper()}_MODEL", raising=False)
    # Faithful to a real fresh install: the factory defaults DO answer the
    # category lookup (default_vision_* → apple/apple-vision). Stubbing this
    # to None is what let #4345's Group Same Documents look green here while
    # the live run resolved to OCR and died mid-run.
    _category_prefix = {"vision": "vision", "llm": "text", "audio": "audio"}

    def _fresh_category_default(category):
        prefix = _category_prefix.get(category)
        if not prefix:
            return None
        provider = FACTORY_AI_DEFAULTS.get(f"default_{prefix}_provider")
        model = FACTORY_AI_DEFAULTS.get(f"default_{prefix}_model")
        return (provider, model) if provider and model else None

    fresh_db = SimpleNamespace(
        get_setting=lambda key: FACTORY_AI_DEFAULTS.get(key),
        get_default_model_for_category=_fresh_category_default,
        get_default_model=lambda: None,
        list_providers=lambda: [_provider("apple")],
        list_models=lambda provider_id: [
            _model("apple-intelligence", ["text"]),
            _model("apple-vision", ["vision"]),
            _model("apple-speech", ["audio", "transcription"]),
        ],
    )
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: fresh_db)
    monkeypatch.setattr("fichero_server.llm.get_api_key", lambda provider: None)

    # The ONLY preset allowed to fail keyless preflight: Translate (DeepL)
    # exists specifically to use the DeepL cloud API — keyless, it must fail
    # AT PREFLIGHT with the provider named (the second #4325 acceptance
    # criterion), not mid-run.
    keyed_presets = {"Translate (DeepL)"}

    # #4345: the second class of honest keyless refusal. Group Same Documents
    # json-parses a VISION answer, and the keyless vision default is Apple
    # Vision OCR — a recognition pass that ignores the prompt. It used to pass
    # preflight and then die mid-run on "Expecting value: line 1 column 1";
    # now it refuses up front, naming the capability to configure.
    # 2026-09-01 (Daniel: "Apple Vision → CSV failed"): the same class, three
    # more presets. `table_extract` and `convert` ask a model to LAY OUT a
    # page as CSV / HTML / Markdown / SVG; their own VisionToolConfig has
    # always said supports_apple_vision=False, but only mid-run — so a
    # keyless install dispatched, priced and logged the run before refusing.
    # The refusal moved to preflight; the verdict is unchanged.
    generative_vision_presets = {
        "Group Same Documents",
        "Accounts → Spreadsheet (CSV)",
        "Extract Table",
        "Convert to HTML",
        "Convert to Markdown",
        "Convert to SVG",
    }

    # 2026-08-26 redesign: the Pipeline preset DELEGATES to the paleography
    # and review workflows, whose staged review passes need a configured,
    # generation-capable vision model — the keyless Apple-OCR default cannot
    # review anything. Refusing up front with the model named is the honest
    # keyless behaviour (same philosophy as the class above), and the
    # refusal must SAY what to configure.
    delegating_presets = {"Transcribe + Review (Pipeline)"}

    failures: dict[str, list[str]] = {}
    for preset in _load_preset_files():
        workflow = to_workflow_def(
            Workflow(
                id=f"keyless-{preset['name']}",
                name=preset["name"],
                nodes=preset.get("nodes", []),
                edges=preset.get("edges", []),
                config=preset.get("config", {}),
            )
        )
        errors = validate_workflow_llm_preflight(
            workflow, LLMConfig(provider="", model="")
        )
        if preset["name"] in keyed_presets:
            assert errors, f"{preset['name']}: expected keyless preflight failure"
            assert any("DeepL" in e and "API key" in e for e in errors), errors
        elif preset["name"] in generative_vision_presets:
            assert errors, f"{preset['name']}: expected keyless preflight failure"
            assert any(
                "generation-capable vision model" in e and "not configured" in e
                for e in errors
            ), errors
        elif preset["name"] in delegating_presets:
            assert errors, f"{preset['name']}: expected keyless preflight failure"
            assert any(
                "on-device model" in e or "not configured" in e for e in errors
            ), errors
        elif errors:
            failures[preset["name"]] = errors

    assert not failures, failures


def test_workflow_level_cloud_default_is_gated_too(monkeypatch):
    """Nodes inheriting the workflow-level provider/model get the same check."""
    _common_env(monkeypatch, api_key=None)
    node = NodeDef(id="summarize", tool="summarize_file")

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="openai", model="gpt-5")
    )

    assert len(errors) == 1
    assert "OpenAI" in errors[0]


# ---------------------------------------------------------------------------
# #4345 — generation-capable model requirement (same preflight, second axis)
# ---------------------------------------------------------------------------


def test_recognition_only_model_predicate_matches_apple_vision_ocr_route():
    """The predicate must track _apple_vision_dispatch's OCR route exactly."""
    from fichero_server.llm import is_recognition_only_vision_model

    assert is_recognition_only_vision_model("apple", "apple-vision")
    assert is_recognition_only_vision_model("apple", "")
    assert is_recognition_only_vision_model("apple", "default")
    assert is_recognition_only_vision_model("Apple", " Apple-Vision ")
    # Generative on-device/cloud vision is fine.
    assert not is_recognition_only_vision_model("apple", "apple-intelligence")
    assert not is_recognition_only_vision_model("openai", "gpt-5")
    assert not is_recognition_only_vision_model("ollama", "llava")


def test_similarity_refuses_ocr_only_vision_model(monkeypatch):
    """similarity json-parses the answer, so OCR can never satisfy it."""
    _common_env(monkeypatch, api_key=None)
    node = NodeDef(
        id="cluster",
        tool="similarity",
        provider_name="apple",
        model_name="apple-vision",
    )

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="", model="")
    )

    assert len(errors) == 1
    assert "generation-capable vision model" in errors[0]
    assert "not configured" in errors[0]
    assert "cluster" in errors[0]


def test_similarity_accepts_a_generative_vision_model(monkeypatch):
    _common_env(monkeypatch, api_key="sk-test")
    node = NodeDef(
        id="cluster",
        tool="similarity",
        provider_name="openai",
        model_name="gpt-5",
    )

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="", model="")
    )

    assert errors == []


def test_ocr_only_model_is_fine_for_a_tool_that_does_not_parse(monkeypatch):
    """The gate is per-tool: transcribe WANTS OCR text and stays ungated."""
    _common_env(monkeypatch, api_key=None)
    node = NodeDef(
        id="transcribe",
        tool="transcribe",
        provider_name="apple",
        model_name="apple-vision",
    )

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="", model="")
    )

    assert errors == []


# ---------------------------------------------------------------------------
# 2026-09-01: a batch-only model must be refused BEFORE the run is paid for.
#
# Daniel ran a workflow and the provider answered "404 This model is only
# available through the Batch API. Use the /api/beta/batches endpoint
# instead." Fichero has no batch client, so the only honest outcome is a
# preflight refusal that names the model — the run had nothing to gain by
# starting.
# ---------------------------------------------------------------------------


def test_batch_only_model_is_refused_before_the_run(monkeypatch):
    _common_env(monkeypatch, api_key="sk-test")
    node = NodeDef(
        id="summarize",
        tool="summarize_file",
        provider_name="openai",
        model_name="gpt-5-batch",
    )

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="openai", model="gpt-5")
    )

    assert errors, "a batch-only model must not reach the run"
    assert "Batch API" in errors[0]
    assert "gpt-5-batch" in errors[0]


def test_an_interactive_model_still_passes(monkeypatch):
    _common_env(monkeypatch, api_key="sk-test")
    node = NodeDef(
        id="summarize",
        tool="summarize_file",
        provider_name="openai",
        model_name="gpt-5",
    )

    assert validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="openai", model="gpt-5")
    ) == []


# ---------------------------------------------------------------------------
# 2026-09-01: "Apple Vision → CSV failed".
#
# 22 vision tools declare supports_apple_vision=False in their own
# VisionToolConfig; exactly one of them ALSO carried
# requires_generative_model=True, so the other 21 refused mid-run instead of
# at preflight. The declaration the tools already make is now the one the
# preflight reads.
# ---------------------------------------------------------------------------


def test_a_tool_that_disowns_apple_vision_is_refused_at_preflight(monkeypatch):
    _common_env(monkeypatch, api_key="sk-test")
    node = NodeDef(
        id="csv",
        tool="table_extract",
        provider_name="apple",
        model_name="apple-vision",
    )

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="apple", model="apple-vision")
    )

    assert errors, "table_extract must not be dispatched onto Apple Vision"
    assert "Apple Vision" in errors[0] or "on-device OCR" in errors[0]


def test_a_tool_that_supports_apple_vision_is_untouched(monkeypatch):
    _common_env(monkeypatch, api_key="sk-test")
    # transcribe DOES support Apple Vision — its whole cheap tier is that
    # path, and refusing it here would break the free on-device lane.
    node = NodeDef(
        id="read",
        tool="transcribe",
        provider_name="apple",
        model_name="apple-vision",
    )

    assert validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="apple", model="apple-vision")
    ) == []


# ---------------------------------------------------------------------------
# 2026-09-01 (Daniel, screenshot): the staged chain read "use apple-vision to
# … → then use apple-vision to Translate". Translation is GENERATION — Apple
# Vision's OCR route ignores the prompt and returns the page's own text — so
# the step could only ever fail. It now fails BEFORE the run is paid for.
# ---------------------------------------------------------------------------


def test_translate_is_refused_on_apple_vision(monkeypatch):
    _common_env(monkeypatch, api_key="sk-test")
    node = NodeDef(
        id="translate",
        tool="translate",
        provider_name="apple",
        model_name="apple-vision",
    )

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="apple", model="apple-vision")
    )

    assert errors, "translate must not be dispatched onto Apple Vision OCR"
    assert "generation-capable" in errors[0], errors
    assert "Translate" in errors[0], errors


def test_text_translate_is_refused_on_apple_vision(monkeypatch):
    _common_env(monkeypatch, api_key="sk-test")
    node = NodeDef(
        id="translate-text",
        tool="text_translate",
        provider_name="apple",
        model_name="apple-vision",
    )

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="apple", model="apple-vision")
    )

    assert errors, "text_translate must not be dispatched onto Apple Vision OCR"
    assert "generation-capable" in errors[0], errors


def test_translate_on_a_generative_model_is_untouched(monkeypatch):
    """The rule refuses the OCR ROUTE, never translation itself.

    Apple Intelligence generates text on-device; a keyless install must keep
    its free translation lane (the regression a blanket flag caused once
    already — keyless Transcribe (Auto-Detect) stopped running).
    """
    _common_env(monkeypatch, api_key=None)
    node = NodeDef(
        id="translate",
        tool="translate",
        provider_name="apple",
        model_name="apple-intelligence",
    )

    assert validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="apple", model="apple-intelligence")
    ) == []
