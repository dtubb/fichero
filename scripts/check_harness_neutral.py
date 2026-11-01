#!/usr/bin/env python3
"""dev-workflows.project.neutral: harness code carries no first-project strings.

The harness must serve other projects; names of this repo's branches, folders, scripts and users belong in
harness.toml. Walks the STRING constants (docstrings skipped) of the harness modules and fails on a hit.
Exempt: the "fichero-server" sys.path import string, FICHERO_* env names."""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
W = "fichero-builder/fichero_builder/"
FILES = [W + f"{m}.py" for m in ("check_tool", "jail", "land_tool", "start_tool", "brief_tool", "policy_hook")] + ["fichero-server/src/fichero_server/workflows/worker_process.py"] + [
    f"scripts/harness_{m}.py" for m in ("check", "land", "review", "start", "policy_hook", "brief", "handoff_hook")]
BAD = re.compile(r"integration|Fichero Projects|lane_ready_check|pipeline/|dtubb|fichero-|scripts/check_")
OK = re.compile(r"fichero-(server|builder)")  # sys.path imports of the engine and the Builder packages


def violations(path) -> list[str]:
    tree = ast.parse(Path(path).read_text())
    doc = {id(n.body[0].value) for n in ast.walk(tree)
           if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
           and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in doc:
            s = OK.sub("", n.value)
            if m := BAD.search(s):
                out.append(f"{path}:{n.lineno}: first-project string {m.group()!r}; move it to harness.toml")
    return out


def main() -> int:
    bad = [v for f in FILES if (ROOT / f).is_file() for v in violations(ROOT / f)]
    print("\n".join(bad) or f"ok: {len(FILES)} harness files are project-neutral")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
