"""What the builder fixes or spells out itself when a guard is red for a mechanical reason (owner 2026-11-14: the builder
hand-holds the lanes, not the manager). Two parts:

- `allowlist_only_removed`: the `allowlist-entries-only-removed` rule class. A pinned guard's allowlist (a top-level literal assigned
  to a name like KNOWN_VIOLATIONS, or a known-gaps / allowlist JSON) that only LOST entries makes the guard stricter, never looser,
  so the ladder judges with head's copy of that one file instead of refusing a pinned-file change.
- `fix_hints`: the exact command for a red that is one, put in the alert or the fix brief: a stale allowlist entry ("drop from the
  set"), a missing `Spec-change:` trailer, stale generated contracts or embed list.
"""
from __future__ import annotations

import ast
import json
import re
import shlex

ALLOWLIST_NAME = re.compile(r"KNOWN|ALLOW|BASELINE|EXEMPT|DEBT", re.I)  # ponytail: by name; a REQUIRED_* list never matches
ALLOWLIST_JSON = re.compile(r"known|allow|baseline|debt|exempt", re.I)


def _literal_items(node) -> list[tuple[str, str]] | None:
    """(key dump, value dump) per entry of a dict/set/list/tuple literal; None for anything else (a call, a comprehension)."""
    if isinstance(node, ast.Dict) and None not in node.keys:
        return [(ast.dump(k), ast.dump(v)) for k, v in zip(node.keys, node.values, strict=True) if k is not None]
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        return [(ast.dump(e), "") for e in node.elts]
    return None


def _assign(stmt) -> tuple[str, object, object] | None:
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
        return stmt.targets[0].id, None, stmt.value
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value is not None:
        return stmt.target.id, ast.dump(stmt.annotation), stmt.value
    return None


def _py_only_removed(before: str, after: str) -> bool:
    try:
        a, b = ast.parse(before), ast.parse(after)
    except SyntaxError:
        return False
    if len(a.body) != len(b.body) or ast.dump(a) == ast.dump(b):
        return False
    for x, y in zip(a.body, b.body, strict=True):
        if ast.dump(x) == ast.dump(y):
            continue
        ax, ay = _assign(x), _assign(y)
        if not ax or not ay or ax[:2] != ay[:2] or not ALLOWLIST_NAME.search(ax[0]) or type(ax[2]) is not type(ay[2]):
            return False
        old, new = _literal_items(ax[2]), _literal_items(ay[2])
        if old is None or new is None or len(new) >= len(old) or any(e not in old for e in new):
            return False
    return True


def _json_subset(new, old) -> bool:
    """Every entry of `new` is in `old`; a kept text value may be reworded (spec: known-gaps-only-removed)."""
    if isinstance(new, dict) and isinstance(old, dict):
        return set(new) <= set(old) and all(_json_subset(new[k], old[k]) or (isinstance(new[k], str) and isinstance(old[k], str)) for k in new)
    if isinstance(new, list) and isinstance(old, list):
        return all(e in old for e in new)
    return new == old


def allowlist_only_removed(path: str, before: str, after: str) -> bool:
    """`allowlist-entries-only-removed`: the file's only change is entries removed from an allowlist (a Python guard: top-level
    literals assigned to a KNOWN/ALLOW/BASELINE/EXEMPT/DEBT name; a JSON whose name says known/allow/baseline/debt/exempt), none
    added, every other statement identical. Comments are free (the AST ignores them)."""
    if path.endswith(".py"):
        return _py_only_removed(before, after)
    if path.endswith(".json") and ALLOWLIST_JSON.search(path.rsplit("/", 1)[-1]):
        try:
            old, new = json.loads(before), json.loads(after)
        except ValueError:
            return False
        return old != new and _json_subset(new, old)
    return False


STALE_HEAD = re.compile(r"(drop from the set|now clean; remove them|remove from)\b[^\n]*:\s*$", re.I)


def stale_keys(output: str) -> list[str]:
    """The entries a guard calls stale: the indented lines under its 'drop from the set:' (or 'now clean; remove them:') line."""
    keys, on = [], False
    for ln in output.splitlines():
        if STALE_HEAD.search(ln):
            on = True
            continue
        if on:
            if not ln.strip() or not ln[:1].isspace() or ln.strip().startswith(("✗", "Fix")):
                on = False
                continue
            keys.append(ln.split()[0].strip("'\""))
    return keys


def entry_lines(text: str, keys: list[str]) -> dict[str, tuple[int, int]]:
    """{key: (first line, last line)} of each key's entry in the file's top-level allowlist literals (a dict entry runs to its value's end)."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    out: dict[str, tuple[int, int]] = {}
    lines = text.splitlines()

    def end(n: int) -> int:  # a parenthesised value's closing `),` is not in the AST: take the lines that are only that
        while n < len(lines) and lines[n].strip() and not lines[n].strip().strip("),"):
            n += 1
        return n
    for stmt in tree.body:
        a = _assign(stmt)
        if not a or not ALLOWLIST_NAME.search(a[0]):
            continue
        node = a[2]
        pairs = list(zip(node.keys, node.values, strict=True)) if isinstance(node, ast.Dict) else [(e, e) for e in getattr(node, "elts", [])]
        for k, v in pairs:
            last = end(v.end_lineno or k.lineno)
            if (isinstance(k, ast.Constant) and k.value in keys and node.lineno < k.lineno and last < (node.end_lineno or 0)
                    and lines[k.lineno - 1].lstrip().startswith(("'", '"'))):  # the entry has its own lines: deleting them leaves valid code
                out[k.value] = (k.lineno, last)
    return out


SPEC_TRAILER_HINT = ("git commit --amend --no-edit --trailer \"Spec-change: <what changed and why>, ruled by the manager\"  "
                     "# the trailer must name the owner's or the manager's ruling (check_spec_acceptance)")
REGEN_RED = re.compile(r"stale|regenerat|out of date|not current|does not match", re.I)


def sections(text: str) -> list[tuple[str, str]]:
    """(guard script path, its output) per `FAIL: scripts/check_x.py` block, the ready script's and the ladder's shape."""
    parts = re.split(r"(?m)^FAIL: (\S+\.py)\s*$", text or "")
    return [(parts[i], parts[i + 1]) for i in range(1, len(parts) - 1, 2)]


def fix_hints(text: str, read, regen: tuple = (), contract_guards: tuple = (), issue: str = "") -> list[str]:
    """The exact command per mechanical red in `text` (blocks of `FAIL: <guard path>` and what it printed). `read(path)` is head's copy
    of a file ('' when absent). One line each; nothing for a red that needs a person."""
    hints = []
    for script, out in sections(text):
        if keys := stale_keys(out):
            spans = entry_lines(read(script), keys)
            if spans and len(spans) == len(keys):
                cmd = " ".join(f"-e '{a}d'" if a == b else f"-e '{a},{b}d'" for a, b in sorted(spans.values()))
                hints.append(f"{script}: stale allowlist entries {', '.join(keys)}: sed -i '' {cmd} {shlex.quote(script)}"
                             " (ruled allowlist-entries-only-removed: the ladder judges with that copy)")
            else:
                hints.append(f"{script}: stale allowlist entries {', '.join(keys)}: remove them from its allowlist (not found as one literal entry each)")
        if "Spec-change:" in out and "check_spec_acceptance" in script:
            hints.append(f"{script}: {SPEC_TRAILER_HINT}")
        if regen and (script in contract_guards or (REGEN_RED.search(out) and re.search(r"contract|openapi|embed|generated", script))):
            msg = f"chore(contract): regenerate the contracts and the engine embed list after the rebase ({issue or 'generated files'})"
            hints.append(f"{script}: regenerate and commit: {' && '.join(regen)} && git add -u && git commit -m {shlex.quote(msg)} -m 'Written-By: <your model>'")
    return list(dict.fromkeys(hints))
