#!/usr/bin/env python3
"""Every registered workflow tool declares what it writes and where it attaches (#5596).

`source.extract.every-output-declares-its-anchor` (docs/contributor_manual/specs/source/
source-model.md, "Extracted data, integrated (review 2026-10-07)"): outside reading and line
finding, most results land as an artifact on a document, not on the page. Each tool's
declaration lives in `fichero_server/workflows/tool_outputs.py`; this guard turns the review
into a checked list. It fails when:

- a registered tool has no declaration (a new tool must say what it writes);
- a declaration names a word outside the vocabulary, or mixes `none` with a record kind;
- a tool writes ONLY a document artifact and is not in the known-gaps baseline
  (`check_tool_outputs_declared_known_gaps.json`), each entry of which names the slice issue
  that moves its output onto the page;
- the baseline is stale: an entry for a tool that is not registered or no longer artifact-only,
  or one that names no slice issue; or a declaration for a tool that is not registered.

Usage:
    scripts/check_tool_outputs_declared.py
    scripts/check_tool_outputs_declared.py --list
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fichero-server" / "src"))

KNOWN_GAPS_PATH = Path(__file__).with_name("check_tool_outputs_declared_known_gaps.json")
#: The slices of the extracted-data review that move an artifact-only output onto the page.
SLICE_ISSUES = frozenset({"#5598", "#5599", "#5600", "#5601", "#5603", "#5604"})
_ISSUE_RE = re.compile(r"#\d+")


def load_known_gaps(path: Path = KNOWN_GAPS_PATH) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"Expected an object mapping in {path}")
    return {str(key): str(value) for key, value in data.items()}


def problems(
    tool_names: Iterable[str],
    declarations: Mapping[str, object],
    known_gaps: Mapping[str, str],
    *,
    writes_vocabulary: frozenset[str],
    anchors_vocabulary: frozenset[str],
) -> list[str]:
    """Every reason the registry, its declarations and the baseline disagree. Empty = pass.

    `declarations` maps a tool name to anything with `writes` (a set of words) and `anchors_at`.
    """
    registered = set(tool_names)
    found: list[str] = []
    artifact_only: set[str] = set()
    for name in sorted(registered):
        declaration = declarations.get(name)
        if declaration is None:
            found.append(f"{name}: registered with no output declaration (workflows/tool_outputs.py)")
            continue
        writes = set(getattr(declaration, "writes", ()) or ())
        anchors_at = getattr(declaration, "anchors_at", None)
        if not writes:
            found.append(f"{name}: declares no writes (use 'none' for a tool that writes nothing)")
        unknown = writes - writes_vocabulary
        if unknown:
            found.append(f"{name}: writes outside the vocabulary: {sorted(unknown)}")
        if "none" in writes and len(writes) > 1:
            found.append(f"{name}: declares 'none' beside record kinds {sorted(writes - {'none'})}")
        if anchors_at not in anchors_vocabulary:
            found.append(f"{name}: anchors_at {anchors_at!r} is not one of {sorted(anchors_vocabulary)}")
        if writes == {"artifact"}:
            artifact_only.add(name)
            if name not in known_gaps:
                found.append(
                    f"{name}: writes only an artifact; declare where its output attaches, "
                    "or seed it in check_tool_outputs_declared_known_gaps.json with its slice issue"
                )
    for name in sorted(set(declarations) - registered):
        found.append(f"{name}: declared in workflows/tool_outputs.py but not a registered tool")
    for name, reason in sorted(known_gaps.items()):
        if name not in registered:
            found.append(f"{name}: known gap for a tool that is not registered (stale baseline)")
        elif name not in artifact_only:
            found.append(f"{name}: known gap but no longer artifact-only; remove it from the baseline")
        if not set(_ISSUE_RE.findall(reason)) & SLICE_ISSUES:
            found.append(f"{name}: known gap names no slice issue ({', '.join(sorted(SLICE_ISSUES))})")
    return found


def _registry() -> tuple[list[str], dict[str, object]]:
    from fichero_server.workflows import registry
    from fichero_server.workflows.tool_outputs import TOOL_OUTPUTS

    # A tool a test registered (a probe or a mock, defined in a test module) is not a product tool: in a full
    # run the suite's earlier tests leave theirs registered, and this real-registry check counted them (M4,
    # 2026-10-10). Run on its own it never sees them.
    names = [tool.name for tool in registry.list_tools()
             if not getattr(registry._TOOLS.get(tool.name), "__module__", "").startswith("tests.")]
    return names, dict(TOOL_OUTPUTS)


def main(argv: list[str]) -> int:
    from fichero_server.workflows.tool_outputs import ANCHORS, WRITES

    names, declarations = _registry()
    known_gaps = load_known_gaps()
    if "--list" in argv:
        for name in sorted(names):
            declaration = declarations.get(name)
            if declaration is None:
                print(f"{name}: UNDECLARED")
            else:
                gap = "  [known gap]" if name in known_gaps else ""
                print(f"{name}: {sorted(declaration.writes)} at {declaration.anchors_at}{gap}")
    found = problems(
        names, declarations, known_gaps, writes_vocabulary=WRITES, anchors_vocabulary=ANCHORS
    )
    if found:
        print(f"check_tool_outputs_declared: {len(found)} problem(s)")
        for line in found:
            print(f"  {line}")
        return 1
    print(
        f"check_tool_outputs_declared: {len(names)} tools declared; "
        f"{len(known_gaps)} artifact-only known gaps"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
