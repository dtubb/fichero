#!/usr/bin/env python3
"""Fail when the committed MCP tools differ from a regeneration of the OpenAPI contract (#5453).

`fichero-mcp/src/fichero_mcp/openapi_tools_generated.py` is written by
`fichero-server/scripts/generate_openapi_mcp.py` from `fichero-server/tests/contracts/openapi.json`:
one tool per operation (`openapi.mcp.current-with-the-contract`). A route added, renamed or
re-documented without regenerating leaves agents without its tool, or with a stale one. This
regenerates in memory, writes nothing, and compares.

    python scripts/check_mcp_generated_current.py [COMMITTED_MODULE]

Exit codes:
    0  the committed module is exactly what the generator writes
    1  it differs: run `python fichero-server/scripts/generate_openapi_mcp.py` and commit
    2  BLIND: the generator, the contract or the committed module could not be read
"""
from __future__ import annotations

import difflib
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATOR = ROOT / "fichero-server" / "scripts" / "generate_openapi_mcp.py"
COMMITTED = ROOT / "fichero-mcp" / "src" / "fichero_mcp" / "openapi_tools_generated.py"


def regenerate() -> str:
    spec = importlib.util.spec_from_file_location("generate_openapi_mcp", GENERATOR)
    if spec is None or spec.loader is None:
        raise OSError(f"cannot load the generator at {GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render()


def main(argv: list[str]) -> int:
    committed_path = Path(argv[0]) if argv else COMMITTED
    try:
        expected = regenerate()
        committed = committed_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 — any failure to read or build is blindness, never a pass
        print(f"✗ BLIND: cannot compare the generated MCP tools: {exc!r}", file=sys.stderr)
        return 2
    if committed == expected:
        print(f"✓ MCP tools current with the OpenAPI contract ({expected.count('    GeneratedTool(')} tools).")
        return 0
    diff = list(difflib.unified_diff(
        committed.splitlines(), expected.splitlines(), "committed", "regenerated", lineterm="", n=1,
    ))
    print("✗ The committed MCP tools differ from the OpenAPI contract. Run:\n"
          "    python fichero-server/scripts/generate_openapi_mcp.py\nand commit the result.", file=sys.stderr)
    print("\n".join(diff[:40]), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
