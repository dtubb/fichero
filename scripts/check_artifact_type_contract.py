#!/usr/bin/env python3
"""Fail when the client queries an artifact type no server path writes (#4420 #4418).

THE DEFECT THIS EXISTS FOR
--------------------------
2026-07-30, #4418. The server gained a producer::

    # importers/ingest.py
    PDF_TEXT_GEOMETRY_ARTIFACT = "text_geometry"
    db.save(Artifact(document_id=..., artifact_type=PDF_TEXT_GEOMETRY_ARTIFACT, ...))

while the client asked for something else::

    // Views/Preview/ImageViewer/OCRGeometryOverlay.swift
    artifactService.getArtifacts(forDocumentId: documentId, type: "transcription")

Two commits, both green, both individually correct. The feature was dead because
nothing compared the two strings. A human found it by reading both files side by
side; no gate could have.

This is a *cross-language contract pair*: one protocol implemented in two
languages, each with passing tests, and no test of the correspondence. The
absence is structural — the Swift suite cannot import the Python writer and the
Python suite cannot exercise the Swift reader — so the check has to live outside
both, which is here. Static extraction, no test process spans the boundary.

WHAT IT DOES AND DOES NOT SEE  (read before trusting a green run)
----------------------------------------------------------------
Producers are resolved from Python AST: a string literal passed as
``artifact_type=``, or a module-level ``NAME = "literal"`` constant referenced
there. Consumers are string literals passed as ``type:`` **inside a
``getArtifacts(...)`` call** in Swift.

Deliberately scoped that way: a bare regex for ``type: "..."`` across the Swift
tree matches thousands of hits in vendored KaTeX JSON and would drown the real
signal. A check that reports noise gets disabled, which is worse than no check.

Many producers are genuinely dynamic — ``artifact_type=artifact_type``,
``tool_config.artifact_type``, ``payload.get(...)``, f-strings. Those CANNOT be
resolved statically. They are counted and reported, never silently dropped:

    a green run means "no mismatch among the values I could resolve",
    NOT "the contract holds".

That distinction is the whole point. A check that examines less than it claims
converts "unknown" into "fine" — see #4425. The unresolved count is printed on
every run, including passing ones, so the limit is never invisible.

If ``artifact_type`` ever becomes a schema enum, replace ``_producers`` with a
read of the enum cases: that is strictly more reliable and removes the dynamic
blind spot. As of 2026-07-30 no such enum exists on any ref — checked.

Exit 0 = no consumer asks for a type nothing produces.
Exit 1 = at least one does, or the corpus came up empty (never pass vacuously).
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

# A consumer value that intentionally has no single producer.
# Keep this SMALL and justify every entry — an allowlist is where a check goes
# to quietly stop working (#2508).
CONSUMER_ALLOWLIST: dict[str, str] = {}

# Artifact types written by the server that no client queries BY NAME.
#
# This is not automatically a defect: `getArtifacts(type:)` is optional and the
# artifacts inspector reads a document's artifacts generically, so most types
# are displayed without ever being named client-side.
#
# It becomes a defect when a producer is added FOR a specific client feature and
# the client asks for a different string — #4418, where ingest wrote
# "text_geometry" and the overlay queried "transcription". A whole-set orphan
# report cannot show that (42 legitimate orphans drown it), so this file is a
# BASELINE: anything produced-but-unqueried and absent here is NEW, and new is
# what needs a human to confirm which of the two it is.
#
# Adding an entry is a claim: "this type is read generically, by design."
_ORPHAN_BASELINE: frozenset[str] = frozenset(
    {
        "analysis", "book_index_topics", "caption", "catalogue", "classification",
        "clean_text", "colors", "comparison", "description", "diagram", "entities",
        "extraction", "extraction_error", "faces", "geo", "handwriting",
        "import_receipt", "key_people", "keywords", "language_identification",
        "layout", "objects", "quality", "questions", "rewrite", "safety", "scene",
        "script_classification", "sentiment", "similarity", "style", "summary",
        "summary_collection", "summary_file", "summary_folder", "table", "tags",
        "timeline", "transcription_review", "translation_review", "video_description",
        # NOTE: "text_geometry" is deliberately ABSENT. It is #4418's live defect —
        # ingest.py writes it for the preview overlay, and OCRGeometryOverlay.swift
        # queries "transcription" instead, so the feature is dead. Add it here only
        # once the overlay reads it, or once someone decides it is generic.
    }
)

_SWIFT_GETARTIFACTS = re.compile(r"getArtifacts\s*\((?P<args>[^)]*)\)", re.S)
_SWIFT_TYPE_ARG = re.compile(r"\btype:\s*\"(?P<val>[A-Za-z0-9_.\-]+)\"")


def _producers(py_root: Path) -> tuple[set[str], list[tuple[str, int, str]]]:
    """(resolvable artifact_type literals, unresolved dynamic sites)."""
    found: set[str] = set()
    dynamic: list[tuple[str, int, str]] = []
    for path in sorted(py_root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        consts: dict[str, str] = {}
        for node in tree.body:  # module-level NAME = "literal" only
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                    and isinstance(node.value.value, str):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        consts[t.id] = node.value.value
        rel = path.relative_to(py_root).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg != "artifact_type":
                    continue
                v = kw.value
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    found.add(v.value)
                elif isinstance(v, ast.Name) and v.id in consts:
                    found.add(consts[v.id])
                else:
                    dynamic.append((rel, node.lineno, ast.unparse(v)[:60]))
    return found, dynamic


def _consumers(swift_root: Path) -> dict[str, list[str]]:
    """artifact type literal -> Swift call sites asking for it."""
    out: dict[str, list[str]] = {}
    for path in sorted(swift_root.rglob("*.swift")):
        try:
            src = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "getArtifacts" not in src:
            continue
        rel = path.as_posix()
        for call in _SWIFT_GETARTIFACTS.finditer(src):
            for m in _SWIFT_TYPE_ARG.finditer(call.group("args")):
                line = src[: call.start()].count("\n") + 1
                out.setdefault(m.group("val"), []).append(f"{rel}:{line}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".", type=Path)
    a = ap.parse_args()
    py = a.repo / "fichero-server" / "src" / "fichero_server"
    sw = a.repo / "fichero" / "fichero"
    for p in (py, sw):
        if not p.is_dir():
            print(f"FAIL: {p} not found — refusing to pass with nothing scanned.", file=sys.stderr)
            return 1

    produced, dynamic = _producers(py)
    consumed = _consumers(sw)
    if not produced or not consumed:
        print("FAIL: extracted an empty producer or consumer set — the extractor "
              "is broken or the layout moved. Refusing to pass vacuously.", file=sys.stderr)
        return 1

    unmatched = {v: s for v, s in consumed.items()
                 if v not in produced and v not in CONSUMER_ALLOWLIST}
    orphans = sorted(produced - set(consumed))
    new_orphans = [o for o in orphans if o not in _ORPHAN_BASELINE]

    print(f"artifact_type contract: {len(produced)} producer value(s), "
          f"{len(consumed)} consumer value(s), "
          f"{len(dynamic)} dynamic producer site(s) NOT statically resolvable.")
    if orphans:
        print(f"note — {len(orphans)} type(s) produced but never queried by name "
              f"({len(orphans) - len(new_orphans)} baselined as generic reads).")

    if new_orphans:
        print(f"\nFAIL: {len(new_orphans)} artifact type(s) written by the server that "
              f"NO client queries, and not baselined as generic:\n")
        for o in new_orphans:
            print(f'  "{o}"')
        print("\nEither a client feature was meant to read this and asks for the wrong\n"
              "string (#4418's shape — both halves green, feature dead), or it is read\n"
              "generically and belongs in _ORPHAN_BASELINE. Decide which; do not guess.")
        return 1

    if not unmatched:
        print("\nOK: every artifact type the client queries is written by some server path.")
        return 0

    print(f"\nFAIL: {len(unmatched)} artifact type(s) queried by the client that no "
          f"server path writes:\n")
    for val, sites in sorted(unmatched.items()):
        print(f'  "{val}"')
        for s in sites:
            print(f"      {s}")
    print("\nEither the client is asking for the wrong string, or the producer was "
          "never written. Both halves can be green while the feature is dead (#4418).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
