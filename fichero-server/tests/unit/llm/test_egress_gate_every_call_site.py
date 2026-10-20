"""`source.egress.every-call-site` and `source.egress.setting-is-reachable`: the gate is INSIDE `get_langchain_model`, so
every caller is covered; and the Set Up places answer is what the gate reads."""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
import importlib.util

# scripts/ is not a package: load the repo's scan helper by path (see test_scan_files_skips_nested_worktrees).
_spec = importlib.util.spec_from_file_location(
    "_scan_files", Path(__file__).resolve().parents[4] / "scripts" / "_scan_files.py")
assert _spec and _spec.loader
scan_files = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan_files)

import pytest
from pydantic import BaseModel

from fichero_server import llm
from fichero_server.llm import LLMConfig, LocalOnlyViolationError

SRC = Path(llm.__file__).parents[1]
CLOUD = ["openai", "anthropic", "google", "mistral"]


def _callers() -> list[tuple[str, str]]:
    """(file, enclosing function) of every call to `get_langchain_model` in the engine's source."""
    found = []
    for path in scan_files.scan_rglob(SRC, "*.py"):
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
    hits = [str(p.relative_to(SRC)) for p in scan_files.scan_rglob(SRC, "*.py")
            if any(w in p.read_text() for w in ("OpenAIEmbeddings(", "init_embeddings(", ".embeddings.create("))]
    assert hits == []


# --- the whole package: every function that opens a network connection is gated or listed with its reason (review 374) ---

_NET = {("httpx", "get"), ("httpx", "post"), ("httpx", "Client"), ("httpx", "AsyncClient"), ("httpx", "request"),
        ("httpx", "stream"), ("aiohttp", "ClientSession"), ("requests", "get"), ("requests", "post"),
        ("requests", "request"), ("request", "urlopen"), ("urllib", "urlopen")}
_GATES = ("check_egress", "_enforce_local_only_provider")

#: Not gated, each with why. None carries what the person's library holds off this Mac.
_OWN_FETCH = "Fichero's own fetch (models, registries, catalogues): no library content"
_SENDS_A_KEY = "sends the API key to the provider the person set up, to list or test models: no library content"
_FETCHES_THE_SOURCE = "fetches FROM the source the person is importing; sends only that source's own URLs"
_LOOPBACK = "talks to a model server on this Mac"
ALLOWED = {
    "api/routes/ai/models.py::_fetch_hf_models": _OWN_FETCH,
    "api/routes/ai/models.py::_fetch_hf_tasks": _OWN_FETCH,
    "api/routes/ai/models.py::get_hf_model": _OWN_FETCH,
    "api/routes/ai/provider_keys.py::test_provider_connection": _SENDS_A_KEY,
    "api/routes/ai/provider_models.py::_live_openrouter_models": _SENDS_A_KEY,
    "api/routes/ai/provider_models.py::_live_huggingface_models": _SENDS_A_KEY,
    "api/routes/ai/provider_models.py::_live_openai_compatible_models": _SENDS_A_KEY,
    "api/routes/ai/provider_models.py::_live_anthropic_models": _SENDS_A_KEY,
    "api/routes/ai/provider_models.py::_live_google_models": _SENDS_A_KEY,
    "api/routes/ai/provider_models.py::list_models_for_provider": _SENDS_A_KEY,
    "llm/__init__.py::_get_shared_httpx_async_client": "built only by _build_langchain_model, which has the gate",
    "llm/kraken_runtime.py::record_files": _OWN_FETCH,
    "llm/local_inference.py::get_json": _LOOPBACK,
    "llm/local_models.py::download_spacy_pipeline": _OWN_FETCH,
    "llm/model_downloads.py::_open": _OWN_FETCH,
    "llm/model_types.py::_refresh_registry_cache": _OWN_FETCH,
    "llm/script_coverage.py::_http_get_bytes": _OWN_FETCH,
    "loaders/iiif_loader.py::load": _FETCHES_THE_SOURCE,
    "media/iiif_fetch.py::urllib_get": _FETCHES_THE_SOURCE,
    "recipes/htr_united.py::_fetch_catalogue": _OWN_FETCH,
}


def _network_functions() -> set[str]:
    found = set()
    for path in scan_files.scan_rglob(SRC, "*.py"):
        for fn in ast.walk(ast.parse(path.read_text())):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                gated = any(g in ast.unparse(fn) for g in _GATES)
                for n in ast.walk(fn):
                    if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                            and isinstance(n.func.value, (ast.Name, ast.Attribute))):
                        base = n.func.value.id if isinstance(n.func.value, ast.Name) else n.func.value.attr
                        if (base, n.func.attr) in _NET and not gated:
                            found.add(f"{path.relative_to(SRC)}::{fn.name}")
    return found


def test_every_function_that_opens_a_connection_is_gated_or_listed_with_its_reason():
    ungated = _network_functions()
    assert ungated - set(ALLOWED) == set(), (
        f"opens a network connection with no egress gate and no reason listed: {sorted(ungated - set(ALLOWED))}")
    assert set(ALLOWED) - ungated == set(), "listed as ungated, but now gated or gone: drop it from ALLOWED"


@pytest.mark.parametrize("place, call", [
    ("cloud", lambda: __import__("fichero_server.media.geo", fromlist=["x"])._geocode_online("Quito", timeout=1)),
    ("cloud", lambda: asyncio.run(__import__("fichero_server.bibliography.doi_lookup", fromlist=["x"]).resolve_doi("10.1/x"))),
])
def test_a_lookup_that_degrades_returns_nothing_instead_of_sending_when_the_cloud_is_not_allowed(
        client, app_db, monkeypatch, place, call):
    import httpx

    monkeypatch.setattr(httpx, "get", lambda *a, **k: pytest.fail("a place name left the Mac"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: pytest.fail("a DOI left the Mac"))
    client.put("/api/recipes/places", json={"places": []})
    assert not call()


def test_the_lookups_that_raise_refuse_in_words_and_another_mac_is_gated_by_its_own_place(client, app_db, monkeypatch):
    from fichero_server.core.egress import EgressRefused, check_egress

    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    check_egress("cloud", what="x", to="y")  # not answered: caps nothing
    client.put("/api/recipes/places", json={"places": ["another-mac"]})
    check_egress("another-mac", what="the copy", to="your other Mac")  # ALLOWED: the answer names it
    with pytest.raises(EgressRefused) as refused:
        check_egress("cloud", what="the name to look up", to="Wikidata")
    assert "Your places do not include a cloud AI service" in str(refused.value) and "Wikidata" in str(refused.value)
    client.put("/api/recipes/places", json={"places": []})
    with pytest.raises(EgressRefused):
        check_egress("another-mac", what="the copy", to="your other Mac")
