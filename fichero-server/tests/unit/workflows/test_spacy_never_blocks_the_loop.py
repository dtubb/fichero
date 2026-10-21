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


def _functions(tree):
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _own_calls(fn):
    """The names this function calls itself: nested defs and lambdas run elsewhere (what `to_thread` is handed)."""
    stack, names = list(fn.body), []
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Call):
            f = node.func
            names.append(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else "")
        stack.extend(ast.iter_child_nodes(node))
    return names, stack


def _entry_points():
    """Every function of the spacy_* modules that reaches a pipeline (a load, or the turn) through the module's own calls."""
    reaching = {"_pipeline", "_load_pipeline", "_load_named", "_turn"}
    modules = [ast.parse((SRC / "knowledge" / f"{m}.py").read_text()) for m in ("spacy_ner", "spacy_svo")]
    calls = {fn.name: set(_own_calls(fn)[0]) for tree in modules for fn in _functions(tree)}
    grew = True
    while grew:
        grew = False
        for name, called in calls.items():
            if name not in reaching and called & reaching:
                reaching.add(name)
                grew = True
    return {n for n in reaching if not n.startswith("_")}


def test_no_async_function_runs_spacy_on_the_loop():
    """The same rule as a guard: an `async def` in the engine calling any pipeline-reaching function of spacy_ner /
    spacy_svo, or a sync helper that calls one (one level, by name), outside a nested function (what `asyncio.to_thread`
    is handed) runs spaCy on the loop."""
    entry = _entry_points()
    assert {"extract_entities", "propose_triples", "predicate_problem"} <= entry, entry
    trees = {path: ast.parse(path.read_text()) for path in SRC.rglob("*.py")
             if path.name not in ("spacy_ner.py", "spacy_svo.py")}
    reaching = set(entry)
    for tree in trees.values():  # sync helpers that call one: `_spacy_page_claims`
        reaching |= {fn.name for fn in _functions(tree) if isinstance(fn, ast.FunctionDef) and set(_own_calls(fn)[0]) & entry}
    bad = [f"{path.relative_to(SRC)}:{fn.lineno} in {fn.name}" for path, tree in trees.items()
           for fn in _functions(tree) if isinstance(fn, ast.AsyncFunctionDef) and set(_own_calls(fn)[0]) & reaching]
    assert not bad, f"spaCy called on the event loop: {bad}"
