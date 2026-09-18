#!/usr/bin/env python3
"""Pins the observable-data-layer rule (#4824): an `@Observable` store's mutating
methods update ONE item in place; they must never call the store's own
`reload()`/`refresh()`/`load…()`, nor reassign the store's list property wholesale
(`items = …`), inside a mutator. Traced 2026-09-18: ArtifactStore, AnnotationStore
both do this on every save/delete, which resets `List(selection:)` and rebuilds
every row on a minor change (the same class as sidebar-crud's `delete.multi`,
already tracked separately — this guardrail does NOT scan call sites, only a
store's own mutating methods; see the spec note on scope).

READ-ONLY: a source scan. It never edits Swift.

Scope: every `.swift` file under `fichero/fichero` declaring a class both
`@Observable` and named `…Store` (found by content, not a hand list) — printed so
an empty scan is visible (finding ZERO stores is a guardrail failure, not a pass:
the scan itself may have broken).

Rule: STRUCTURAL, not lexical — inside ANY non-private method of a store class
OTHER than the load/reload/refresh family (whatever the method is named: `get…`
counts exactly like `add…`), a call to `reload(`/`refresh(`/`load…(` on self, or
a bare reassignment of one of the class's own array-typed stored properties
(`items = …`, never `items[i] = …` / `.append` / `.removeAll(where:)`), is a
finding. Naming a method `getAnnotation` does not exempt it: a lexical
add/create/update/delete/rename/move/promote/apply verb-list was tried first and
missed exactly this shape (#4824) — a `get…` accessor that reassigns the store's
list as a side effect is just as much a wholesale-reload violation as a named
mutator. The store's own `load`/`reload`/`refresh` methods are exempt (that's
THEIR job); so are private helpers (`private func`/`fileprivate func`), since
they cannot be a public mutation surface by themselves — whichever public/
internal method calls them is what gets scanned and flagged.

Allowlist: `scripts/store_wholesale_reload_allowlist.json`, entries
`{file, method, class, reason, issue?}` — shrink-only, same contract as every
other allowlist in this repo: a stale entry (no longer a real finding) or one
missing a `reason` is itself a failure. No automated write path — hand-edit only.

Every entry declares a `class`, decided by READING the method (never by its
name alone — `getAnnotation` proved names lie):
  - `"violation"` — mutates ONE item and must be fixed to splice in place.
    Requires `reason` + `issue`. Counted and reported as DEBT.
  - `"by-design"` — legitimately replaces the whole list because the list's
    own IDENTITY changed (scope / query / sort / an explicit resync) — there
    is no prior item to splice against. Requires `reason` naming which of
    those it is; cites no issue. Reported separately, NOT counted as debt.
    A `by-design` entry whose method name starts with an obvious single-item
    verb (add/create/update/delete/remove/rename/patch/merge/link/set…) is
    refused unless its `reason` names the list-identity axis explicitly
    (scope/query/sort/resync) — a cheap lexical tripwire so a real mutator
    can't be laundered into `by-design` by simply relabeling it.

Run:
    python scripts/check_store_wholesale_reload.py
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path("fichero/fichero")
ALLOWLIST_PATH = pathlib.Path("scripts/store_wholesale_reload_allowlist.json")

_CLASS_RE = re.compile(r"\b(?:final\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*Store)\b")
_FUNC_RE = re.compile(r"\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)")
_ARRAY_PROP_RE = re.compile(
    r"^\s*(?:private\(set\)\s+)?var\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*\["
)
_EXEMPT_PREFIXES = ("load", "reload", "refresh")
_PRIVATE_FUNC_LINE_RE = re.compile(r"\b(?:private|fileprivate)\b.*\bfunc\b")
_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")

_SINGLE_ITEM_VERBS = (
    "add", "create", "update", "delete", "remove", "rename", "patch",
    "merge", "link", "set",
)
_BY_DESIGN_JUSTIFICATION_RE = re.compile(
    r"\b(scope|identity|query|sort|resync)\b", re.IGNORECASE
)


def _looks_like_single_item_verb(method: str) -> bool:
    lowered = method.lower()
    return any(lowered.startswith(v) for v in _SINGLE_ITEM_VERBS)


def _by_design_reason_justifies(reason: str) -> bool:
    return bool(_BY_DESIGN_JUSTIFICATION_RE.search(reason))


def _is_reload_call(identifier: str) -> bool:
    """`reload`/`refresh` exactly, `load…` as a prefix (`loadSomething`), or
    `…Reload`/`…Refresh` as a suffix (`scheduleReload`) — camelCase-aware so a
    call like `downloadModel(` (starts with `down`, not `load`) is never
    mistaken for one, and `scheduleReload(` (no word boundary before `Reload`)
    still matches."""
    lowered = identifier.lower()
    return (
        lowered in ("reload", "refresh")
        or lowered.startswith("load")
        or lowered.endswith("reload")
        or lowered.endswith("refresh")
    )


def _has_reload_call(line: str) -> bool:
    return any(_is_reload_call(m.group(1)) for m in _CALL_RE.finditer(line))


def _is_private_line(line: str) -> bool:
    return bool(_PRIVATE_FUNC_LINE_RE.search(line))


def _is_exempt_name(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith(_EXEMPT_PREFIXES)


def _matching_brace_end(lines: list[str], start_idx: int) -> int:
    """Index PAST the line whose closing brace ends the block that opens
    somewhere at or after `start_idx` — a multi-line `class`/`func` signature
    (parameters spanning several lines before the opening `{`) is handled by
    scanning FORWARD for the first `{` before counting depth, not assuming
    `start_idx`'s own line holds it. Returns len(lines) if unterminated
    (malformed source — never crash the scan)."""
    n = len(lines)
    i = start_idx
    while i < n and "{" not in lines[i]:
        i += 1
    if i >= n:
        return n
    depth = lines[i].count("{") - lines[i].count("}")
    j = i + 1
    while j < n and depth > 0:
        depth += lines[j].count("{") - lines[j].count("}")
        j += 1
    return j


def _is_observable(lines: list[str], class_line_idx: int, lookback: int = 6) -> bool:
    start = max(0, class_line_idx - lookback)
    return any("@Observable" in lines[i] for i in range(start, class_line_idx))


def find_store_classes(text: str) -> list[tuple[str, int, int]]:
    """[(class_name, body_start_idx, body_end_idx)] for every `@Observable
    …Store` class in this file's text (0-indexed line ranges, body_end
    exclusive)."""
    lines = text.splitlines()
    out: list[tuple[str, int, int]] = []
    for i, line in enumerate(lines):
        m = _CLASS_RE.search(line)
        if not m:
            continue
        if not _is_observable(lines, i):
            continue
        end = _matching_brace_end(lines, i)
        out.append((m.group(1), i, end))
    return out


def find_array_properties(lines: list[str], body_start: int, body_end: int) -> set[str]:
    """Top-level (depth-1, i.e. not inside a nested method) array-typed stored
    properties of the class body — a cheap approximation: any `var name: [...`
    line inside the class range that is NOT inside a `func` block."""
    props: set[str] = set()
    i = body_start + 1
    while i < body_end:
        if _FUNC_RE.search(lines[i]):
            i = _matching_brace_end(lines, i)
            continue
        m = _ARRAY_PROP_RE.match(lines[i])
        if m:
            props.add(m.group(1))
        i += 1
    return props


def find_methods(lines: list[str], body_start: int, body_end: int) -> list[tuple[str, int, int]]:
    """[(method_name, body_start_idx, body_end_idx)] for every non-private,
    non-fileprivate `func` directly inside this class body (not nested inside
    another func). A `private`/`fileprivate` method is skipped here — it isn't
    a mutation surface on its own; whatever public/internal method calls it is
    what gets scanned and flagged."""
    out: list[tuple[str, int, int]] = []
    i = body_start + 1
    while i < body_end:
        m = _FUNC_RE.search(lines[i])
        if m:
            end = _matching_brace_end(lines, i)
            if not _is_private_line(lines[i]):
                out.append((m.group(1), i, min(end, body_end)))
            i = end
            continue
        i += 1
    return out


def _wholesale_reassignment(line: str, prop: str) -> bool:
    if re.search(rf"\b{re.escape(prop)}\s*\[", line):
        return False  # indexed splice: items[idx] = …
    if re.search(rf"\b{re.escape(prop)}\.(append|remove|removeAll|insert)\b", line):
        return False  # in-place mutation
    return bool(re.search(rf"\b{re.escape(prop)}\s*=\s*(?!=)", line))


_LINE_COMMENT_RE = re.compile(r"(?<!:)//.*")


def _decomment_line(line: str) -> str:
    """Strip a trailing `//` line comment so prose mentioning `refresh()` in a
    doc comment never matches as code. Blunt (doesn't handle `//` inside a
    string literal), but this codebase's store files don't need more."""
    return _LINE_COMMENT_RE.sub("", line)


def scan_file(path: pathlib.Path) -> tuple[int, list[dict]]:
    """(store_classes_found, findings) for one Swift file."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    raw_lines = text.splitlines()
    lines = [_decomment_line(line) for line in raw_lines]
    classes = find_store_classes(text)
    findings: list[dict] = []
    for class_name, body_start, body_end in classes:
        array_props = find_array_properties(lines, body_start, body_end)
        for method_name, m_start, m_end in find_methods(lines, body_start, body_end):
            if _is_exempt_name(method_name):
                continue
            for i in range(m_start, m_end):
                line = lines[i]
                if _has_reload_call(line):
                    findings.append({
                        "file": str(path), "line": i + 1, "class": class_name,
                        "method": method_name,
                        "reason": f"calls a reload/refresh/load method inside a mutator: {line.strip()!r}",
                    })
                for prop in array_props:
                    if _wholesale_reassignment(line, prop):
                        findings.append({
                            "file": str(path), "line": i + 1, "class": class_name,
                            "method": method_name,
                            "reason": f"reassigns `{prop}` wholesale instead of splicing: {line.strip()!r}",
                        })
    return len(classes), findings


def scan_tree() -> tuple[int, list[dict]]:
    total_classes = 0
    all_findings: list[dict] = []
    for path in sorted(ROOT.rglob("*.swift")):
        if "@Observable" not in path.read_text(encoding="utf-8", errors="ignore"):
            continue
        n, findings = scan_file(path)
        total_classes += n
        all_findings.extend(findings)
    return total_classes, all_findings


def _load_allowlist() -> list[dict]:
    if not ALLOWLIST_PATH.exists():
        return []
    try:
        return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL check_store_wholesale_reload: {ALLOWLIST_PATH} is malformed JSON: {exc}",
              file=sys.stderr)
        sys.exit(2)


def check() -> int:
    total_classes, findings = scan_tree()
    print(f"Scanned {total_classes} `@Observable` store class(es) under {ROOT}.")
    if total_classes == 0:
        print("FAIL check_store_wholesale_reload: found ZERO @Observable store classes — "
              "the scan itself is broken (the tree moved, or the detector regressed), "
              "not a clean result.", file=sys.stderr)
        return 2

    allowlist = _load_allowlist()
    allowed_keys = set()
    violation_keys: set[tuple[str, str]] = set()
    by_design_keys: set[tuple[str, str]] = set()
    failures: list[str] = []
    for entry in allowlist:
        key = (entry.get("file"), entry.get("method"))
        reason = (entry.get("reason") or "").strip()
        cls = entry.get("class")
        if cls not in ("violation", "by-design"):
            failures.append(
                f"{ALLOWLIST_PATH}: entry for {key} has no valid `class` "
                f"('violation' or 'by-design'), got {cls!r}."
            )
            continue
        if not reason:
            failures.append(f"{ALLOWLIST_PATH}: entry for {key} has no `reason`.")
            continue
        if cls == "violation":
            if not entry.get("issue"):
                failures.append(f"{ALLOWLIST_PATH}: violation entry for {key} has no `issue`.")
                continue
            violation_keys.add(key)
        else:  # by-design
            method = entry.get("method") or ""
            if _looks_like_single_item_verb(method) and not _by_design_reason_justifies(reason):
                failures.append(
                    f"{ALLOWLIST_PATH}: by-design entry for {key} looks like a single-item "
                    f"mutator by name — its `reason` must name the list-identity axis "
                    f"(scope/query/sort/resync) that changed, or it belongs in `violation`."
                )
                continue
            by_design_keys.add(key)
        allowed_keys.add(key)

    current_keys = {(f["file"], f["method"]) for f in findings}
    stale = allowed_keys - current_keys
    for key in sorted(stale):
        kind = "by-design" if key in by_design_keys else "violation"
        failures.append(
            f"{ALLOWLIST_PATH}: allowlisted {kind} {key} no longer occurs — remove it (shrink-only)."
        )

    unallowlisted = [f for f in findings if (f["file"], f["method"]) not in allowed_keys]

    if unallowlisted:
        print(f"\n{len(unallowlisted)} NEW finding(s) (not allowlisted):")
        for f in unallowlisted:
            print(f"  {f['file']}:{f['line']} {f['class']}.{f['method']} — {f['reason']}")
    if failures:
        print(f"\n{len(failures)} allowlist problem(s):")
        for msg in failures:
            print(f"  - {msg}")

    debt = len([f for f in findings if (f["file"], f["method"]) in violation_keys])
    by_design = len([f for f in findings if (f["file"], f["method"]) in by_design_keys])

    if unallowlisted or failures:
        print(
            f"\nFAIL check_store_wholesale_reload: {len(unallowlisted)} new finding(s), "
            f"{len(failures)} allowlist problem(s). "
            f"{debt} violation(s) [DEBT], {by_design} by-design (not counted as debt)."
        )
        return 1

    print(
        f"OK check_store_wholesale_reload: {len(findings)} finding(s) — "
        f"{debt} violation(s) [DEBT], {by_design} by-design, all allowlisted with a reason."
    )
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python scripts/check_store_wholesale_reload.py", file=sys.stderr)
        return 2
    return check()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
