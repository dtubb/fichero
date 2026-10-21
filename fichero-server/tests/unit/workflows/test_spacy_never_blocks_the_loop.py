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
            # `self.f()` is a method, whatever a module-level function of the same name does
            names.append(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute)
                         and not (isinstance(f.value, ast.Name) and f.value.id in ("self", "cls")) else "")
        stack.extend(ast.iter_child_nodes(node))
    return names


def _runs_spacy(src=SRC):
    """The names of every function in the engine that runs a spaCy pipeline, by name: seeded from where a pipeline is loaded
    (`load_spacy_pipeline`, a `spacy.load(...)` call), followed through the sync functions that call one to a fixed point,
    across every module, and through `from m import f as g` aliases (a call is matched by its name, wherever it is read)."""
    trees = [ast.parse(path.read_text()) for path in src.rglob("*.py")]
    # Module-level functions only: a method is called by a name every class shares (`__init__`, `run`), which would sweep in the engine.
    sync = [fn for tree in trees for fn in tree.body if isinstance(fn, ast.FunctionDef)]
    defined_in = {}  # name -> the modules (last path part) that define it at module level
    for path in src.rglob("*.py"):
        for fn in ast.parse(path.read_text()).body:
            if isinstance(fn, ast.FunctionDef):
                defined_in.setdefault(fn.name, set()).add(path.stem)
    # `from m import f as g`: g runs spaCy when f does AND m is a module that defines that f (not another `f`)
    aliases = {a.asname: (a.name, (n.module or "").rsplit(".", 1)[-1]) for tree in trees for n in ast.walk(tree)
               if isinstance(n, ast.ImportFrom) for a in n.names if a.asname}
    reaching = {"load_spacy_pipeline"}
    loaders = [fn for fn in sync if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "load"
                                        and isinstance(n.func.value, ast.Name) and n.func.value.id == "spacy"
                                        for n in ast.walk(fn))]
    reaching |= {fn.name for fn in loaders}
    calls = {}
    for fn in sync:
        calls.setdefault(fn.name, set()).update(_own_calls(fn))
    grew = True
    while grew:
        grew = False
        reaching |= {alias for alias, (name, module) in aliases.items() if name in reaching and module in defined_in.get(name, ())}
        for name, called in calls.items():
            if name not in reaching and called & reaching:
                reaching.add(name)
                grew = True
    return reaching


def test_no_async_function_runs_spacy_on_the_loop():
    """The guard: an `async def` in the engine calling a function that runs a spaCy pipeline (found from the pipeline loads, to a
    fixed point, across every module, through aliased imports), outside a nested function (what `asyncio.to_thread` is handed),
    runs spaCy on the loop (`runtime.spacy.never-blocks`)."""
    reaching = _runs_spacy()
    assert {"extract_entities", "propose_triples", "predicate_problem", "_spacy_page_claims"} <= reaching, sorted(reaching)
    bad = [f"{path.relative_to(SRC)}:{fn.lineno} in {fn.name}" for path in SRC.rglob("*.py")
           for fn in _functions(ast.parse(path.read_text())) if isinstance(fn, ast.AsyncFunctionDef)
           and set(_own_calls(fn)) & reaching]
    assert not bad, f"spaCy called on the event loop: {bad}"


def _async_offenders(src):
    reaching = _runs_spacy(src)
    return [fn.name for path in src.rglob("*.py") for fn in _functions(ast.parse(path.read_text()))
            if isinstance(fn, ast.AsyncFunctionDef) and set(_own_calls(fn)) & reaching]


def test_the_guard_follows_helpers_across_modules_and_aliased_imports(tmp_path):
    (tmp_path / "loader.py").write_text("import spacy\n\ndef open_it(name):\n    return spacy.load(name)\n")
    (tmp_path / "mid.py").write_text("from loader import open_it\n\ndef parse(text):\n    return open_it('es')(text)\n\n"
                                     "def twice(text):\n    return parse(text)\n")
    (tmp_path / "use.py").write_text(
        "from mid import twice as t\nimport mid\n\nasync def direct(x):\n    return mid.parse(x)\n\n"
        "async def aliased(x):\n    return t(x)\n\nasync def threaded(x):\n    return await to_thread(t, x)\n\n"
        "async def other(x):\n    return len(x)\n")
    assert sorted(_async_offenders(tmp_path)) == ["aliased", "direct"]
