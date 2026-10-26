"""The MCP face: per-role tools over `core.API` (pipeline.three-faces). A coder gets report/ask/done, a reviewer
verdict, a manager the dispatch tools. Approve and answer are never here: a model cannot answer its own question.
Run: python -m pipeline.mcp_server --role coder (stdio; Pi loads it through pipeline/pi-agent/mcp.json)."""
from __future__ import annotations

import argparse
import json

from pipeline import core


def tools_for(role: str) -> dict:
    return {name: core.API[name] for name in core.ROLE_TOOLS[role]}


def served(role: str) -> tuple[str, ...]:
    """What the server lists: the one worker list for every worker role (cache), the manager's own for the manager."""
    return core.ROLE_TOOLS[role] if role == "manager" else core.WORKER_TOOLS


def build(role: str):
    from mcp.server.fastmcp import FastMCP  # the repo venv has the mcp SDK

    server = FastMCP(f"pipeline-{role}")
    for name in served(role):
        fn = core.API[name]
        server.tool(name=name, description=(fn.__doc__ or name).strip().splitlines()[0])(_wrap(fn, name in core.ROLE_TOOLS[role]))
    return server


def _wrap(fn, allowed: bool = True):
    import inspect

    def tool(**kwargs):
        if not allowed:  # listed for every worker (one tool list), refused for this role
            return {"error": f"`{fn.__name__}` is not this role's tool"}
        try:
            return json.loads(json.dumps(fn(**kwargs), default=str))  # plain JSON types, whatever the function returns
        except Exception as e:  # noqa: BLE001 - the model gets the error text, the state does not move
            return {"error": f"{type(e).__name__}: {e}"}

    # the parameters are the function's; the return annotation is dropped, or FastMCP would validate a `dict`
    # declaration against the list that `queue` returns (seen live on 2026-10-25 as a string-vs-dict error)
    tool.__name__, tool.__doc__ = fn.__name__, fn.__doc__
    tool.__signature__ = inspect.signature(fn).replace(return_annotation=inspect.Signature.empty)
    tool.__annotations__ = {k: v for k, v in getattr(fn, "__annotations__", {}).items() if k != "return"}
    return tool


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--role", choices=sorted(core.ROLE_TOOLS), default="coder")
    args = p.parse_args()
    build(args.role).run()


if __name__ == "__main__":
    main()
