"""Every tool registers the same way: by being imported in tools/__init__.py (#3951).

zoom and consistency_check were special-cased inside
`registry._load_tool_implementations()` instead. They worked only because that
function ran eagerly at module import — the moment tool loading was deferred
they vanished from the registry silently, and the paleography ensemble depends
on both. These tests make that impossible to reintroduce.

The check is deliberately a SNAPSHOT derived from the source, not a hand-written
list: a hand-list would have to be updated by the same person who forgot to add
the import in the first place.
"""

from __future__ import annotations

import ast
from pathlib import Path

import fichero_server.api.main  # noqa: F401  — breaks the fichero_server.db <-> api.main import cycle
from fichero_server.workflows import registry


def _tools_imported_by_init() -> set[str]:
    """Tool module names imported by tools/__init__.py, read from its AST."""
    init = Path(registry.__file__).parent / "tools" / "__init__.py"
    tree = ast.parse(init.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "fichero_server.workflows.tools":
            names.update(alias.name for alias in node.names)
    return names


def test_zoom_and_consistency_check_register_via_tools_init() -> None:
    """The two that were special-cased (#3951). Named explicitly: they regressed."""
    imported = _tools_imported_by_init()
    assert "zoom" in imported, (
        "zoom must be imported in tools/__init__.py like every other tool — "
        "registering it only in registry._load_tool_implementations() means it "
        "disappears the moment tool loading is deferred (#3951)"
    )
    assert "consistency_check" in imported, (
        "consistency_check must be imported in tools/__init__.py (#3951)"
    )


def test_registry_special_cases_no_individual_tools() -> None:
    """The tool loader imports the PACKAGE, never individual tools.

    The loader was `_load_tool_implementations` (eager, called at module
    import) and is now `_ensure_tools_loaded` (lazy, called from every read
    path) as of #3950. The invariant is unchanged and is what this asserts:
    whatever loads the tools must import the package as a whole, because a
    tool listed individually here registers only on that path and vanishes
    the moment loading moves (#3951).
    """
    source = Path(registry.__file__).read_text()
    assert "def _ensure_tools_loaded" in source, (
        "the tool loader has been renamed again — retarget this test at it "
        "rather than deleting it; it is the #3951 guard"
    )
    start = source.index("def _ensure_tools_loaded")
    body = source[start : source.index("\n\n\n", start)]
    offenders = [
        line.strip()
        for line in body.splitlines()
        if "from fichero_server.workflows.tools import" in line
    ]
    assert not offenders, (
        "registry._load_tool_implementations() must import the tools PACKAGE only. "
        f"Individually-imported tools register ONLY on the eager path and vanish "
        f"when loading is deferred (#3951). Move these into tools/__init__.py: {offenders}"
    )


def test_the_regressed_tools_are_actually_registered() -> None:
    """The two that vanished are present after a normal import (#3951).

    Deliberately NOT "every module in __init__ maps to a tool of the same name" —
    that is false: `sources`, `agent`, `mcp` and others each register several
    tools under unrelated names. The honest invariant is that the tools which
    actually regressed are reachable by the normal path.
    """
    import fichero_server.workflows.tools  # noqa: F401  — trigger the decorators

    registered = set(registry.TOOLS.keys())
    for name in ("zoom", "consistency-check"):
        assert name in registered, (
            f"{name!r} is missing from the registry — it regressed once by being "
            f"registered only inside _load_tool_implementations() (#3951). "
            f"Registered tools: {len(registered)}"
        )
