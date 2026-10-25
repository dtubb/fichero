"""The MCP face: per-role tools over `core.API` (pipeline.three-faces). A coder gets report/ask/done, a reviewer
verdict, a manager the dispatch tools. Approve and answer are never here: a model cannot answer its own question.
Run: python -m pipeline.mcp_server --role coder (stdio; Pi loads it through pipeline/pi-agent/mcp.json)."""
from __future__ import annotations

import argparse
import json

from pipeline import core


def tools_for(role: str) -> dict:
    return {name: core.API[name] for name in core.ROLE_TOOLS[role]}


def build(role: str):
    from mcp.server.fastmcp import FastMCP  # the repo venv has the mcp SDK

    server = FastMCP(f"pipeline-{role}")
    for name, fn in tools_for(role).items():
        server.tool(name=name, description=(fn.__doc__ or name).strip().splitlines()[0])(_wrap(fn))
    return server


def _wrap(fn):
    def tool(**kwargs) -> str:
        try:
            return json.dumps(fn(**kwargs), default=str)
        except Exception as e:  # noqa: BLE001 - the model gets the error text, the state does not move
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    tool.__name__, tool.__doc__ = fn.__name__, fn.__doc__
    tool.__signature__ = __import__("inspect").signature(fn)
    tool.__annotations__ = dict(getattr(fn, "__annotations__", {}))
    return tool


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--role", choices=sorted(core.ROLE_TOOLS), default="coder")
    args = p.parse_args()
    build(args.role).run()


if __name__ == "__main__":
    main()
