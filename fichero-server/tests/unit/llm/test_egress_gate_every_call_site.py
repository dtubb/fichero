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
