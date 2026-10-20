"""`source.egress.every-call-site` and `source.egress.setting-is-reachable`: the gate is INSIDE `get_langchain_model`, so
every caller is covered; and the Set Up places answer is what the gate reads."""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest
from pydantic import BaseModel

from fichero_server import llm
from fichero_server.llm import LLMConfig, LocalOnlyViolationError

SRC = Path(llm.__file__).parents[1]
CLOUD = ["openai", "anthropic", "google", "mistral"]


def _callers() -> list[tuple[str, str]]:
    """(file, enclosing function) of every call to `get_langchain_model` in the engine's source."""
    found = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for node in ast.walk(fn):
                    if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "get_langchain_model":
                        found.append((str(path.relative_to(SRC)), fn.name))
    return sorted(set(found))


def test_the_gate_is_inside_the_model_factory_and_every_caller_is_in_the_llm_module_or_the_chat_route():
    factory = next(n for n in ast.walk(ast.parse((SRC / "llm/__init__.py").read_text()))
                   if isinstance(n, ast.FunctionDef) and n.name == "get_langchain_model")
    assert "_enforce_local_only_provider" in ast.unparse(factory), "the gate is in the factory, not left to each caller"
    outside = {f for f, _ in _callers() if f not in {"llm/__init__.py", "api/routes/system/chat.py"}}
    assert outside == set(), f"a new caller of the model factory outside the reviewed ones: {outside}; add a case below"


@pytest.mark.parametrize("provider", CLOUD)
def test_a_local_only_project_refuses_a_cloud_provider_through_the_factory_and_each_caller(monkeypatch, provider):
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")
    config = LLMConfig(provider=provider, model="m")
    with pytest.raises(LocalOnlyViolationError):
        llm.get_langchain_model(config)

    class Schema(BaseModel):
        x: int = 0

    for call in (lambda: llm.chat_with_tools("hi", [], config), lambda: llm.structured_output("hi", Schema, config)):
        with pytest.raises(LocalOnlyViolationError):  # the two the review found skipping the gate
            asyncio.run(call())


def test_answering_nothing_leaves_in_set_up_refuses_a_cloud_call_in_words(client, app_db, monkeypatch):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    assert client.put("/api/recipes/places", json={"places": []}).status_code == 200
    assert llm.is_local_only() is True, "the places answer is what is_local_only reads"
    with pytest.raises(LocalOnlyViolationError) as refused:
        llm.get_langchain_model(LLMConfig(provider="openai", model="m"))
    assert "Your places do not include a cloud AI service" in str(refused.value)


def test_allowing_another_mac_does_not_open_the_cloud_and_unanswered_caps_nothing(client, app_db, monkeypatch):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    assert llm.is_local_only() is False  # not answered yet: an existing install behaves as before
    client.put("/api/recipes/places", json={"places": ["another-mac"]})
    assert llm.is_local_only() is False
    with pytest.raises(LocalOnlyViolationError):
        llm.get_langchain_model(LLMConfig(provider="openai", model="m"))


# --- the clients that are not the model factory: transcription, translation, the Hugging Face API, OCR, embeddings ---

_CLIENTS = {"ClientSession", "OpenAIWhisperParser", "AsyncClient", "ChatOpenAI", "AzureChatOpenAI", "init_chat_model"}


def test_every_outbound_client_in_the_llm_module_is_built_behind_the_gate():
    """Each function that builds a network client calls the gate itself, or is an internal of the factory whose only
    caller already did. A new client without the gate fails here."""
    tree = ast.parse((SRC / "llm/__init__.py").read_text())
    ungated = []
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            built = {getattr(n.func, "attr", getattr(n.func, "id", "")) for n in ast.walk(fn) if isinstance(n, ast.Call)} & _CLIENTS
            if built and "_enforce_local_only_provider" not in ast.unparse(fn):
                ungated.append(fn.name)
    # the shared httpx client is made only for `_build_langchain_model`, which has the gate
    assert sorted(ungated) == ["_get_shared_httpx_async_client"], ungated
    callers = {fn.name for fn in ast.walk(tree) if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
               and "_get_shared_httpx_async_client(" in ast.unparse(fn)} - {"_get_shared_httpx_async_client"}
    assert callers == {"_build_langchain_model"}


@pytest.mark.parametrize("provider", ["deepl", "openai"])
def test_translation_and_transcription_clients_refuse_when_local_only(monkeypatch, provider):
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")
    config = LLMConfig(provider=provider, model="m")
    with pytest.raises(LocalOnlyViolationError):
        asyncio.run(llm._translate_with_deepl(text="x", source_lang="auto", target_lang="en", config=config))
    with pytest.raises(LocalOnlyViolationError):
        asyncio.run(llm.audio_transcription("/nonexistent.wav", "p", config))


def test_a_cloud_ocr_provider_meets_the_same_check_as_a_model_call(client, app_db, monkeypatch):
    from fichero_server.media.ocr_geometry import OCRCloudProviderBlocked, enforce_ocr_provider_policy

    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    enforce_ocr_provider_policy("google_vision")  # not answered: caps nothing
    client.put("/api/recipes/places", json={"places": []})
    for provider in ("google_vision", "aws_textract", "azure_document_intelligence"):
        with pytest.raises(OCRCloudProviderBlocked) as refused:
            enforce_ocr_provider_policy(provider)
        assert "Your places do not include a cloud AI service" in str(refused.value)
    enforce_ocr_provider_policy("apple_vision")  # on this Mac: allowed


def test_no_cloud_embeddings_client_exists_and_a_new_one_must_be_gated():
    """Embeddings run in fastembed on this Mac (`db/embeddings.py`). If a cloud embeddings client is ever added, this
    fails until it is built behind the gate and listed in `_CLIENTS`."""
    hits = [str(p.relative_to(SRC)) for p in SRC.rglob("*.py")
            if any(w in p.read_text() for w in ("OpenAIEmbeddings(", "init_embeddings(", ".embeddings.create("))]
    assert hits == []
