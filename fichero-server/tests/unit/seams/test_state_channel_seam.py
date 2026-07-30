"""Seam category 2 — LangGraph state channels (#4420).

The archetype is #4283. ``_detect_empty_text_output`` gated on
``state["files"]``. Three places read that key, one place built it, and it was
never a declared member of the ``State`` TypedDict — so LangGraph dropped
every write and the read always returned nothing. A silent-run guard was
structurally unreachable for all sixteen workflow families, its unit tests
passed the whole time (they hand-built a state carrying ``files``), and
nobody knew for weeks.

The rule this module enforces is mechanical and needs no judgement:

    every key READ from graph state must be a DECLARED channel,
    and every key WRITTEN to graph state must be a DECLARED channel.

An undeclared channel is not a style problem. LangGraph merges node results
into the state by channel; a key that is not a channel is silently discarded,
so reader and writer can both look perfectly correct in review while nothing
flows between them. That is the definition of a seam defect.

SCOPE — deliberately narrow, to keep the signal honest. Only names *typed as*
graph state count:

* any function parameter annotated ``State``, and
* ``final_state`` / ``channel_values`` / ``terminal_state``, which are the
  names the runner and checkpointer use for the merged channel values.

That scoping matters. The runner also keeps a *different* dict called
``state`` — the ``_running_workflows`` registry entry, holding ``status``,
``events``, ``final_state``. Counting those reads produced pure noise on the
first pass. Two unrelated things named ``state`` in one module is its own
readability hazard, but it is not this sweep's finding to make.

Findings are reported, not fixed (#4420). A legitimately one-sided channel
gets an ``ALLOWED_UNDECLARED`` entry with a reason, and the allowlist is
bidirectionally hygienic: a stale entry fails too, so the exception list
cannot rot into a second place where defects hide.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "fichero_server"
TYPES_MODULE = SRC / "workflows" / "types.py"

# Names that always denote merged graph channel values.
GRAPH_STATE_NAMES = frozenset({"final_state", "channel_values", "terminal_state"})

# Directories whose functions participate in graph execution.
SCANNED_PACKAGES = ("workflows", "execution")

# Keys that may legitimately be read from graph state without being declared
# channels. Each entry MUST carry a reason. Empty today: every undeclared key
# the sweep currently finds is a real finding, reported in #4420.
ALLOWED_UNDECLARED: dict[str, str] = {}


def _declared_channels() -> set[str]:
    tree = ast.parse(TYPES_MODULE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "State":
            return {
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            }
    return set()


def _annotation_is_state(annotation: ast.expr | None) -> bool:
    return annotation is not None and "State" in ast.unparse(annotation)


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for package in SCANNED_PACKAGES:
        files.extend(sorted((SRC / package).rglob("*.py")))
    return files


def _collect() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return (reads, writes) as key -> ['module.py:line', ...]."""
    reads: dict[str, list[str]] = defaultdict(list)
    writes: dict[str, list[str]] = defaultdict(list)

    for path in _scanned_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = str(path.relative_to(SRC))

        for fn in [
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]:
            names = set(GRAPH_STATE_NAMES)
            for arg in list(fn.args.args) + list(fn.args.kwonlyargs):
                if _annotation_is_state(arg.annotation):
                    names.add(arg.arg)

            for node in ast.walk(fn):
                # state.get("key")
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in names
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    reads[node.args[0].value].append(f"{rel}:{node.lineno}")
                # state["key"] — read or write depending on context
                if (
                    isinstance(node, ast.Subscript)
                    and isinstance(node.value, ast.Name)
                    and node.value.id in names
                    and isinstance(node.slice, ast.Constant)
                    and isinstance(node.slice.value, str)
                ):
                    bucket = writes if isinstance(node.ctx, ast.Store) else reads
                    bucket[node.slice.value].append(f"{rel}:{node.lineno}")

    return dict(reads), dict(writes)


def _format(keys: dict[str, list[str]]) -> str:
    return "\n  ".join(
        f"{key!r} — read at {', '.join(sites[:4])}"
        + (f" (+{len(sites) - 4} more)" if len(sites) > 4 else "")
        for key, sites in sorted(keys.items())
    )


def test_the_sweep_has_something_to_scan():
    """Guard the guard (#4382): a sweep that scans nothing must fail."""
    assert TYPES_MODULE.is_file(), f"State definition missing: {TYPES_MODULE}"
    declared = _declared_channels()
    assert len(declared) >= 15, (
        f"only {len(declared)} State channels parsed from {TYPES_MODULE} — the "
        "sweep below would pass vacuously"
    )
    files = _scanned_files()
    assert len(files) >= 40, (
        f"only {len(files)} modules found under {SCANNED_PACKAGES} — nothing "
        "meaningful is being scanned"
    )
    reads, _ = _collect()
    assert len(reads) >= 10, (
        f"only {len(reads)} distinct graph-state reads detected — the AST "
        "matcher has stopped recognising the access pattern"
    )


def test_every_key_read_from_graph_state_is_a_declared_channel():
    """A read of an undeclared channel can only ever return nothing."""
    declared = _declared_channels()
    reads, _writes = _collect()
    undeclared = {
        key: sites
        for key, sites in reads.items()
        if key not in declared and key not in ALLOWED_UNDECLARED
    }
    assert undeclared == {}, (
        f"{len(undeclared)} key(s) are read from LangGraph state but are not "
        "declared channels on State (workflows/types.py). LangGraph discards "
        "writes to undeclared keys, so each of these reads returns nothing "
        "however correct the writer looks — the #4283 shape:\n  "
        + _format(undeclared)
    )


def test_every_key_written_to_graph_state_is_a_declared_channel():
    """A write to an undeclared channel is silently dropped."""
    declared = _declared_channels()
    _reads, writes = _collect()
    undeclared = {
        key: sites
        for key, sites in writes.items()
        if key not in declared and key not in ALLOWED_UNDECLARED
    }
    assert undeclared == {}, (
        f"{len(undeclared)} key(s) are written to LangGraph state without "
        "being declared channels; the write is dropped on merge:\n  "
        + _format(undeclared)
    )


def test_allowlist_has_no_stale_entries():
    """Bidirectional hygiene: an exception that no longer applies must fail.

    Without this, ALLOWED_UNDECLARED becomes a second place defects hide —
    exactly the failure mode that let a stale KNOWN_VIOLATIONS entry sit in
    the AppKit guardrail.
    """
    declared = _declared_channels()
    reads, writes = _collect()
    seen = set(reads) | set(writes)

    stale_declared = sorted(k for k in ALLOWED_UNDECLARED if k in declared)
    assert stale_declared == [], (
        "these keys are allowlisted as undeclared but ARE now declared "
        f"channels — drop them from ALLOWED_UNDECLARED: {stale_declared}"
    )
    stale_unused = sorted(k for k in ALLOWED_UNDECLARED if k not in seen)
    assert stale_unused == [], (
        "these allowlist entries match no state access at all — the code "
        f"they excused is gone: {stale_unused}"
    )
    missing_reason = sorted(
        k for k, reason in ALLOWED_UNDECLARED.items() if not str(reason).strip()
    )
    assert missing_reason == [], (
        f"allowlist entries without a reason: {missing_reason}"
    )
