"""spaCy never runs on the event loop (`runtime.spacy.never-blocks`, #5843 family): a page's names wait for the spaCy
turn and run the pipeline on a worker thread, so a slow or contended spaCy leaves the loop answering."""
from __future__ import annotations

import ast
import asyncio
import time
from pathlib import Path

from fichero_server.knowledge import spacy_ner
from fichero_server.workflows.ner.providers import SpacyNERProvider

SRC = Path(__file__).resolve().parents[3] / "src" / "fichero_server"
SPACY_CALLS = {"extract_entities", "cluster_aliases"}


def test_the_loop_keeps_answering_while_spacy_is_held_up(monkeypatch):
    monkeypatch.setattr(spacy_ner, "extract_entities", lambda *a, **k: time.sleep(1.0) or [])

    async def go() -> float:
        worst, last = 0.0, time.monotonic()
        work = asyncio.create_task(SpacyNERProvider().extract("Don Juan de Mosquera vendió una casa.", language="es"))
        while not work.done():
            await asyncio.sleep(0.02)
            now = time.monotonic()
            worst, last = max(worst, now - last), now
        await work
        return worst

    assert asyncio.run(go()) < 0.3, "the event loop was held while spaCy ran"


def test_no_async_function_calls_spacy_directly():
    """The same rule as a guard: an `async def` in the engine calling `spacy_ner.extract_entities`/`cluster_aliases`
    outside a nested function (what `asyncio.to_thread` is handed) runs it on the loop."""
    bad = []
    for path in SRC.rglob("*.py"):
        if path.name == "spacy_ner.py":
            continue
        for fn in (n for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, ast.AsyncFunctionDef)):
            stack = list(fn.body)
            while stack:  # this function's own statements: nested defs and lambdas run elsewhere
                node = stack.pop()
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    continue
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in SPACY_CALLS
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "spacy_ner"):
                    bad.append(f"{path.relative_to(SRC)}:{node.lineno} in {fn.name}")
                stack.extend(ast.iter_child_nodes(node))
    assert not bad, f"spaCy called on the event loop: {bad}"
