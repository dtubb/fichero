"""A generated tool says whether it reads or changes data (#5584, `openapi.mcp.reads-say-so` in
`docs/contributor_manual/specs/harness/surfaces-from-openapi.md`).

An agent onboarding a project was told `recipes assemble` changes data; it proposes a recipe and writes
nothing. A route that takes its question as a body but writes nothing carries `x-fichero-reads: true` in the
contract (the route's `openapi_extra`), and its tool says it reads.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from fichero_mcp import openapi_tools_generated as generated

REPO = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((REPO / "fichero-server" / "tests" / "contracts" / "openapi.json").read_text())


def _generator():
    if "generate_openapi_mcp" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "generate_openapi_mcp", REPO / "fichero-server" / "scripts" / "generate_openapi_mcp.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["generate_openapi_mcp"] = module
        spec.loader.exec_module(module)
    return sys.modules["generate_openapi_mcp"], sys.modules["openapi_operations"]


generator, operations_module = _generator()


def _op(path: str, method: str):
    return next(op for op in operations_module._build_operations(CONTRACT)
                if op.path == path and op.method == method)


def test_openapi_mcp_reads_say_so__assemble_is_a_read():
    """openapi.mcp.reads-say-so: "a route that takes its question as a body but writes nothing (`POST
    /api/recipes/assemble`) is marked a read in the contract ... and its tool says it reads rather than
    "changes data".\""""
    assert CONTRACT["paths"]["/api/recipes/assemble"]["post"].get("x-fichero-reads") is True
    assert _op("/api/recipes/assemble", "POST").reads
    doc = generated.fichero_recipes_assemble.__doc__
    assert "toolset `recipes`; reads)" in doc and "changes data" not in doc


def test_openapi_mcp_reads_say_so__a_write_still_says_it_changes_data():
    """WHY: the mark is opt-in per route; every other POST/PUT/PATCH/DELETE still says it changes data, and a
    GET still reads."""
    assert "changes data" in generated.fichero_recipes_save_project_setup.__doc__
    assert not _op("/api/recipes/project", "PUT").reads
    assert _op("/api/recipes/project", "GET").reads


def test_openapi_mcp_reads_say_so__the_generator_reads_the_mark():
    """WHY: the generator, not a hand edit, writes the word: a contract that marks a POST a read makes its
    tool say so."""
    contract = json.loads(json.dumps(CONTRACT))
    contract["paths"]["/api/recipes/check"]["post"]["x-fichero-reads"] = True
    op = next(o for o in operations_module._build_operations(contract)
              if o.path == "/api/recipes/check" and o.method == "POST")
    assert "toolset `recipes`; reads)" in generator._docstring(op)
