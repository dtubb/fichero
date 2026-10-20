"""`ai.where.one-egress-gate` / `.egress-at-every-call` (#5368): every model call that leaves this Mac meets the project's
rule. A project that has not said yes to cloud models sends NOTHING, whichever path made the call (a workflow, the chat's
tool and structured calls, a vision read, an MCP request that names the library), and says why in words."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from fichero_server import llm
from fichero_server.llm import EgressRefusedError, LLMConfig, LocalOnlyViolationError
from fichero_server.llm import egress
from fichero_server.observability import episodes

CLOUD = LLMConfig(provider="openai", model="gpt-test", api_key="sk-test")


@pytest.fixture(autouse=True)
def _engine_switch_off(monkeypatch):
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "0")
    egress._CACHE.clear()


@pytest.fixture
def sent(monkeypatch):
    """Every model the engine builds for a call: a refused call builds none, so nothing can be sent."""
    built: list[LLMConfig] = []

    class _Model:
        def bind_tools(self, tools):
            return self

        def with_structured_output(self, schema):
            return self

        async def ainvoke(self, *a, **k):
            raise RuntimeError("the fake provider was reached")

    monkeypatch.setattr(llm, "_build_langchain_model", lambda config: built.append(config) or _Model())
    return built


def _project(tmp_path: Path, answers: str | None) -> str:
    """A library folder whose Set Up said `answers` (None: Set Up never ran)."""
    folder = tmp_path / "Proj.fichero" / "recipe"
    folder.mkdir(parents=True)
    if answers is not None:
        (folder / "setup.yaml").write_text(answers, encoding="utf-8")
    return str(tmp_path / "Proj.fichero")


def _under(library: str):
    token = episodes.set_library(library)
    return lambda: episodes._episode_library_path.reset(token)


CALLS = {
    "workflow chat": lambda: llm.chat("Hello", CLOUD),
    "chat with tools": lambda: llm.chat_with_tools("Hello", [], CLOUD),
    "structured output": lambda: llm.structured_output("Hello", dict, CLOUD),
    "vision": lambda: llm.vision(["data:image/png;base64,AAAA"], "Read this", CLOUD),
}


@pytest.mark.parametrize("answers", ["cloud_allowed: false\n", None, "cloud_allowed: yes please\n", "{not: [yaml"])
@pytest.mark.parametrize("path", sorted(CALLS))
def test_a_project_that_has_not_said_yes_sends_nothing_on_any_path(tmp_path, sent, path, answers):
    done = _under(_project(tmp_path, answers))
    try:
        with pytest.raises(EgressRefusedError) as refused:
            asyncio.run(CALLS[path]())
    finally:
        done()
    assert sent == []
    words = str(refused.value)
    assert "keeps its pages on this Mac" in words and "openai" in words and "Set Up" in words


def test_a_project_that_said_yes_may_send(tmp_path, sent):
    done = _under(_project(tmp_path, "cloud_allowed: true\n"))
    try:
        with pytest.raises(RuntimeError, match="fake provider was reached"):
            asyncio.run(llm.chat("Hello", CLOUD))
    finally:
        done()
    assert [c.provider for c in sent] == ["openai"]


def test_the_rule_is_read_again_when_the_project_changes_it(tmp_path, sent):
    library = _project(tmp_path, "cloud_allowed: true\n")
    done = _under(library)
    try:
        llm.get_langchain_model(CLOUD)
        setup = Path(library) / "recipe" / "setup.yaml"
        setup.write_text("cloud_allowed: false\n", encoding="utf-8")
        import os
        os.utime(setup, (setup.stat().st_atime, setup.stat().st_mtime + 5))
        with pytest.raises(EgressRefusedError):
            llm.get_langchain_model(CLOUD)
    finally:
        done()


def test_a_model_on_this_mac_is_never_asked_of_the_project(tmp_path, sent):
    done = _under(_project(tmp_path, "cloud_allowed: false\n"))
    try:
        llm.get_langchain_model(LLMConfig(provider="ollama", model="llama3.2", api_base="http://127.0.0.1:11434"))
    finally:
        done()
    assert len(sent) == 1


def test_a_call_under_no_library_meets_only_the_engine_wide_switch(sent, monkeypatch):
    llm.get_langchain_model(CLOUD)
    assert len(sent) == 1
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")
    with pytest.raises(LocalOnlyViolationError) as refused:
        llm.get_langchain_model(CLOUD)
    assert not isinstance(refused.value, EgressRefusedError)


def test_the_refusal_is_the_typed_egress_failure_the_run_reports(tmp_path):
    from fichero_server.execution.runner import _typed_failure

    assert _typed_failure(EgressRefusedError("openai", model="gpt-test", kind="chat"))["category"] == "egress_refused"


def test_a_request_that_names_a_library_runs_under_that_project(tmp_path):
    """The MCP and the chat reach the engine over HTTP with the library header: the request IS the project's."""
    from fastapi.testclient import TestClient

    from fichero_server.api.main import app

    seen: list[str | None] = []
    app.add_api_route("/api/__egress_probe", lambda: seen.append(egress.current_library()) or {}, methods=["GET"])
    try:
        library = _project(tmp_path, "cloud_allowed: false\n")
        TestClient(app).get("/api/__egress_probe", headers={"X-Fichero-Library-Path": library})
        TestClient(app).get("/api/__egress_probe")
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/api/__egress_probe"]
    assert seen == [library, None]


# -- the sweep: every way a provider client is built or called goes through the gate ---------------------------------
SRC = Path(llm.__file__).parent.parent


def test_the_one_factory_builds_every_provider_client_and_the_gate_is_its_first_act():
    """A provider SDK is imported only inside `llm/__init__.py`, and `get_langchain_model` (the only way to a built model)
    meets the gate before it looks in its cache."""
    sdk = ("langchain_openai", "langchain_anthropic", "langchain_google_genai", "langchain_ollama", "langchain_groq",
           "langchain_mistralai", "openai", "anthropic")
    offenders = []
    for path in SRC.rglob("*.py"):
        if path == Path(llm.__file__):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            if any(n.split(".")[0] in sdk for n in names):
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert offenders == [], f"a provider client outside the gate's factory: {offenders}"
    factory = next(n for n in ast.parse(Path(llm.__file__).read_text(encoding="utf-8")).body
                   if isinstance(n, ast.FunctionDef) and n.name == "get_langchain_model")
    gate = [i for i, n in enumerate(factory.body) if "_enforce_local_only_provider" in ast.dump(n)]
    cache = [i for i, n in enumerate(factory.body) if "_langchain_model_cache_key" in ast.dump(n)]
    assert gate and cache and gate[0] < cache[0]


def test_every_call_that_builds_no_model_meets_the_gate_itself():
    """A call that does not go through `get_langchain_model` (the Hub's inference API, audio) enforces on its own: the
    functions that open a connection to a provider's host are exactly the ones that call the gate."""
    tree = ast.parse(Path(llm.__file__).read_text(encoding="utf-8"))
    hosts = ("api-inference.huggingface.co", "audio.transcriptions", "audio/transcriptions", "OpenAIWhisperParser")
    for fn in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        body = ast.get_source_segment(Path(llm.__file__).read_text(encoding="utf-8"), fn) or ""
        if any(h in body for h in hosts):
            assert "_enforce_local_only_provider" in body, f"{fn.name} reaches a provider without the gate"
