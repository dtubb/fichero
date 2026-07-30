"""Seam category 3 — knowledge-graph writes must announce themselves (#4420).

The archetype is #4392. ``KnowledgeGraphInspectorSection`` observes
``ClaimStore.changeToken`` and reloads correctly when it bumps. The view is
not the problem — nothing was telling it. ``kg_writer.py`` persists claims and
entities and emits no ``claim.*`` / ``entity.*`` change event, so on the
catalogue preset (where ``persist_kg`` is off and ``kg_writer`` is the node
that writes) rows land in the database and the inspector keeps showing what
it loaded when the document was opened.

WHY THE EXISTING GUARDRAIL MISSED IT — the open question in #4392, settled.

``scripts/check_emit_change_coverage.py`` does **not** fail open; it exits
non-zero against an empty tree, so it is not one of #4382's thirty. The
problem is its rule. The non-route scan flags "saves of observable models"
by looking for the model NAME near a ``.save(`` in the same file.
``kg_writer.py`` contains neither: it calls ``_write_kg_rows``, imported from
``extractors``, which imports ``upsert_entity`` / ``save_claim`` from
``_entity_writer`` *inside the function body*. The persistence is two hops
away behind a shared helper, so the scanner has nothing to match on and
reports no gap. That is the worse of the two possible answers — a guardrail
that runs, passes, and cannot see the defect class.

WHAT THIS SWEEP DOES DIFFERENTLY. It follows the call graph instead of
matching text in one file:

1. seed with functions that directly ``.save()`` a KG model;
2. propagate two bounded rounds through calls **resolved via each module's
   own imports** — so ``save`` means the ``save`` that module actually
   imported, not every function of that name in the repo;
3. flag any ``workflows/tools`` module that reaches a KG-persisting helper
   and never calls a change emitter.

Both details are load-bearing. Unbounded closure over bare names marks 2957
functions as persisting AND emitting, flagging nothing; the same closure
without import resolution flags 76 modules, mostly through generic names like
``get_database``. With resolution and a depth bound it is 5, all verified by
hand.

``emit_progress_event`` is deliberately NOT counted as a change emitter. It
publishes to the per-run progress stream, which no store observes. Treating
it as an emitter would excuse ``cleanup.py`` and ``import_artifacts.py``,
and mistaking progress for change is close to the original defect.

Findings are reported, not fixed (#4420).
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "fichero_server"

KG_MODELS = frozenset({"KnowledgeClaim", "KnowledgeClaimLink", "KnowledgeEntity"})
CHANGE_EMITTERS = frozenset({"emit_change", "emit_workflow_kg_changes"})
TOOLS_PREFIX = "workflows/tools/"
PROPAGATION_ROUNDS = 2

# Modules that may persist KG rows without emitting, each with a reason.
# Empty: every module the sweep currently flags was read and is a real
# finding, reported on #4392.
ALLOWED_SILENT_WRITERS: dict[str, str] = {}


def _modules() -> dict[str, ast.Module]:
    out: dict[str, ast.Module] = {}
    for path in sorted(SRC.rglob("*.py")):
        try:
            out[str(path.relative_to(SRC))] = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
    return out


def _module_key(dotted: str | None) -> str | None:
    if not dotted or not dotted.startswith("fichero_server."):
        return None
    return dotted[len("fichero_server.") :].replace(".", "/") + ".py"


def _imported_names(tree: ast.Module) -> dict[str, str]:
    """Local name -> defining module path, for in-project imports only."""
    resolved: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            key = _module_key(node.module)
            if key:
                for alias in node.names:
                    resolved[alias.asname or alias.name] = key
    return resolved


def _functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Attribute):
                names.add(func.attr)
            elif isinstance(func, ast.Name):
                names.add(func.id)
    return names


def _kg_persisting_functions(modules: dict[str, ast.Module]) -> set[tuple[str, str]]:
    """(module, function) pairs that persist KG rows, directly or via imports."""
    persisting: set[tuple[str, str]] = set()
    for module, tree in modules.items():
        for fn in _functions(tree):
            body = ast.unparse(fn)
            if ".save(" in body and any(model in body for model in KG_MODELS):
                persisting.add((module, fn.name))

    for _round in range(PROPAGATION_ROUNDS):
        for module, tree in modules.items():
            imports = _imported_names(tree)
            local = {fn.name for fn in _functions(tree)}
            for fn in _functions(tree):
                if (module, fn.name) in persisting:
                    continue
                for name in _called_names(fn):
                    if name in imports:
                        target = (imports[name], name)
                    elif name in local:
                        target = (module, name)
                    else:
                        continue
                    if target in persisting:
                        persisting.add((module, fn.name))
                        break
    return persisting


def _silent_kg_writers() -> dict[str, list[str]]:
    """tools module -> resolved persisting helpers it calls without emitting."""
    modules = _modules()
    persisting = _kg_persisting_functions(modules)
    findings: dict[str, list[str]] = {}

    for module, tree in modules.items():
        if not module.startswith(TOOLS_PREFIX) or module in ALLOWED_SILENT_WRITERS:
            continue
        module_calls = _called_names(tree)
        if module_calls & CHANGE_EMITTERS:
            continue
        imports = _imported_names(tree)
        local = {fn.name for fn in _functions(tree)}
        reached = sorted(
            name
            for name in module_calls
            if (
                (imports[name], name)
                if name in imports
                else ((module, name) if name in local else None)
            )
            in persisting
        )
        if reached:
            findings[module] = reached
    return findings


def test_the_sweep_has_something_to_scan():
    """Guard the guard (#4382)."""
    modules = _modules()
    assert len(modules) >= 200, f"only {len(modules)} modules parsed under {SRC}"
    tools = [m for m in modules if m.startswith(TOOLS_PREFIX)]
    assert len(tools) >= 50, f"only {len(tools)} workflow tool modules found"
    persisting = _kg_persisting_functions(modules)
    assert len(persisting) >= 40, (
        f"only {len(persisting)} KG-persisting functions resolved — the call "
        "graph walk has stopped working and this sweep would pass vacuously"
    )
    assert any(name == "_write_kg_rows" for _module, name in persisting), (
        "_write_kg_rows is no longer recognised as persisting KG rows — the "
        "shared-helper hop this sweep exists to follow is not being followed"
    )


def test_every_kg_writing_tool_emits_a_change_event():
    """A KG write nothing announces leaves every observer showing stale data."""
    findings = _silent_kg_writers()
    rendered = "\n  ".join(
        f"{module} — reaches {', '.join(helpers[:3])}"
        for module, helpers in sorted(findings.items())
    )
    assert findings == {}, (
        f"{len(findings)} workflow tool module(s) persist knowledge-graph rows "
        "and never emit a change event. The rows land, no event is published, "
        "ClaimStore.changeToken never bumps, and the inspector goes on showing "
        "what it loaded when the document was opened (#4392):\n  " + rendered
    )


def test_kg_writer_emits_a_change_event():
    """#4392 itself, addressable on its own so its fix shows as this going green."""
    findings = _silent_kg_writers()
    assert f"{TOOLS_PREFIX}kg_writer.py" not in findings, (
        "kg_writer persists KG rows via _write_kg_rows and emits no change "
        "event; on the catalogue preset it is THE node that writes, so the "
        "Knowledge Graph inspector never updates after a run (#4392)"
    )


def test_progress_events_are_not_mistaken_for_change_events():
    """emit_progress_event must never satisfy this contract.

    It publishes to the per-run progress stream, which no store observes.
    Counting it would excuse exactly the modules that emit progress and
    nothing else — and confusing the two is the original defect in miniature.
    """
    assert "emit_progress_event" not in CHANGE_EMITTERS
    modules = _modules()
    progress_only = [
        module
        for module, tree in modules.items()
        if module.startswith(TOOLS_PREFIX)
        and "emit_progress_event" in _called_names(tree)
        and not (_called_names(tree) & CHANGE_EMITTERS)
    ]
    assert progress_only, (
        "no progress-only tool module found — this test can no longer "
        "demonstrate the distinction it exists to protect"
    )


def test_allowlist_has_no_stale_entries():
    """Bidirectional hygiene: an excused module that now emits must fail."""
    modules = _modules()
    stale_missing = sorted(m for m in ALLOWED_SILENT_WRITERS if m not in modules)
    assert stale_missing == [], (
        f"allowlisted modules that no longer exist: {stale_missing}"
    )
    now_emitting = sorted(
        m
        for m in ALLOWED_SILENT_WRITERS
        if m in modules and (_called_names(modules[m]) & CHANGE_EMITTERS)
    )
    assert now_emitting == [], (
        f"these modules now emit change events — drop the exception: {now_emitting}"
    )
    missing_reason = sorted(
        m for m, reason in ALLOWED_SILENT_WRITERS.items() if not str(reason).strip()
    )
    assert missing_reason == [], f"entries without a reason: {missing_reason}"
