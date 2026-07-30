"""Guard: fichero-mcp declares its own `mcp` bounds (#4337).

`mcp` 2.0 removed `mcp.server.fastmcp` — FastMCP became
`mcp.server.mcpserver.MCPServer`. Every tool module in this package
(`server.py`, `full.py`, `simple.py`) does `from mcp.server.fastmcp import
FastMCP`, so an unbounded install resolves 2.x and the product does not import
at all: no failing call, no error at runtime, just six modules that cannot be
loaded.

The constraint is also declared in `fichero-server/pyproject.toml` (the bundle
manifest), but this is the package that actually does the import, and it can be
installed on its own. A constraint that only exists in a *sibling* package is a
constraint that goes missing the moment the dependency edge changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomllib


def _dependencies() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]  # fichero-mcp/
    with open(root / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)
    out: dict[str, str] = {}
    for requirement in data["project"]["dependencies"]:
        name = requirement.strip()
        for sep in ("[", ">", "<", "=", "!", "~", ";", " "):
            name = name.split(sep, 1)[0]
        out[name.strip().lower()] = requirement.strip()[len(name.strip()) :].strip()
    return out


def test_mcp_is_capped_below_2():
    specifier = _dependencies().get("mcp")
    assert specifier is not None, "fichero-mcp must declare mcp itself"
    assert "<2" in specifier.replace(" ", ""), (
        f"fichero-mcp declares mcp{specifier} — needs a <2 ceiling. mcp 2.x "
        "removed mcp.server.fastmcp, which server.py/full.py/simple.py import."
    )


def test_mcp_floor_covers_the_known_advisory():
    specifier = _dependencies()["mcp"]
    assert ">=1.28.1" in specifier.replace(" ", ""), (
        f"fichero-mcp declares mcp{specifier} — needs >=1.28.1 (PYSEC-2026-3483)."
    )


def test_fastmcp_import_path_still_exists():
    """The import the ceiling exists to protect actually resolves."""
    from mcp.server.fastmcp import FastMCP

    assert callable(FastMCP)


@pytest.mark.parametrize("module", ["server", "full", "simple"])
def test_tool_modules_import(module):
    """Each entry-point module loads — this is what mcp 2.x silently breaks."""
    import importlib

    loaded = importlib.import_module(f"fichero_mcp.{module}")
    assert loaded is not None


def test_parser_handles_bounded_and_bare_requirements():
    """Fixture proving the specifier split is not accidentally always empty."""
    deps = _dependencies()
    assert deps["fichero-server"] == "", deps["fichero-server"]
    assert deps["mcp"].startswith(">="), deps["mcp"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
