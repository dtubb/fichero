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
blind spot. A Swift `enum ArtifactType: String` DOES exist (Models/Artifact.swift) and is
checked below; there is no Python-side enum as of 2026-07-30.

Exit 0 = no consumer asks for a type nothing produces.
Exit 1 = at least one does, or the corpus came up empty (never pass vacuously).
"""

from __future__ import annotations

import argparse
import ast
import re
import sys

from _check_floor import require_scan_floor
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
        # "catalogue.chunk" is a GENERIC read: catalogue.py writes per-chunk
        # summaries and the inspector's artifact list renders them like any
        # other artifact, with no by-name query. Baselined, not deleted — the
        # rows are user-visible, they are simply not fetched by type.
        "catalogue.chunk",
        # "dates" (#3322): a per-document provenance record of historical-date
        # extraction. The QUERYABLE surface is the Document date_* columns
        # (sort/filter read those); the artifact rides the generic artifact
        # browser like catalogue.chunk. Generic read, not a dead feature.
        "dates",
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

_SWIFT_ENUM = re.compile(
    r"enum\s+ArtifactType\s*:\s*String\s*\{(?P<body>.*?)\n\s*\}", re.S
)
_SWIFT_ENUM_CASE = re.compile(r"^\s*case\s+(?P<name>[A-Za-z0-9_]+)\s*$", re.M)

_SWIFT_GETARTIFACTS = re.compile(r"getArtifacts\s*\((?P<args>[^)]*)\)", re.S)
_SWIFT_TYPE_ARG = re.compile(r"\btype:\s*\"(?P<val>[A-Za-z0-9_.\-]+)\"")
_SWIFT_LET_LIST = re.compile(
    r"static\s+let\s+(?P<name>[A-Za-z0-9_]+)\s*(?::\s*\[String\]\s*)?=\s*\[(?P<body>[^\]]*)\]"
)
_SWIFT_STR = re.compile(r"\"(?P<val>[A-Za-z0-9_.\-]+)\"")


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


def _swift_type_lists(swift_root: Path) -> dict[str, tuple[list[str], str]]:
    """`static let NAME = ["a", "b"]` -> (values, "file:line").

    A client can ask for a type through a named constant instead of a literal —
    `OCRGeometrySelection.geometryBearingTypes` is exactly that. Reading only
    literals made those reads invisible and reported a live consumer as an
    orphan, which is the wrong direction for this check to be wrong in: a false
    "nothing reads this" invites deleting a feature that works.
    """
    out: dict[str, tuple[list[str], str]] = {}
    for path in sorted(swift_root.rglob("*.swift")):
        try:
            src = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for m in _SWIFT_LET_LIST.finditer(src):
            values = _SWIFT_STR.findall(m.group("body"))
            if values:
                line = src[: m.start()].count("\n") + 1
                out[m.group("name")] = (values, f"{path.as_posix()}:{line}")
    return out


def _consumers(swift_root: Path) -> dict[str, list[str]]:
    """artifact type literal -> Swift call sites asking for it."""
    out: dict[str, list[str]] = {}
    type_lists = _swift_type_lists(swift_root)
    for path in sorted(swift_root.rglob("*.swift")):
        try:
            src = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "getArtifacts" not in src:
            continue
        rel = path.as_posix()
        for call in _SWIFT_GETARTIFACTS.finditer(src):
            args = call.group("args")
            line = src[: call.start()].count("\n") + 1
            for m in _SWIFT_TYPE_ARG.finditer(args):
                out.setdefault(m.group("val"), []).append(f"{rel}:{line}")
            # `type: someVar` where the loop variable comes from a known list —
            # credit every value that list can supply.
            for name, (values, origin) in type_lists.items():
                if re.search(rf"\b{re.escape(name)}\b", src):
                    for value in values:
                        out.setdefault(value, []).append(f"{rel}:{line} (via {origin})")
    return out


def _enum_cases(swift_root: Path) -> tuple[set[str], str | None]:
    """Swift `enum ArtifactType: String` cases — a THIRD declaration of the contract.

    The server writes artifact_type strings, the client queries some by name, and
    this enum names a set independently of both. Three declarations, no mechanism
    keeping them in agreement.
    """
    for path in sorted(swift_root.rglob("*.swift")):
        try:
            src = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        m = _SWIFT_ENUM.search(src)
        if m:
            return set(_SWIFT_ENUM_CASE.findall(m.group("body"))), path.as_posix()
    return set(), None


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
    # #4487: upgraded from an exactly-zero refusal (rc=1) to half-count scan
    # floors with the BLIND exit — a half-dead extractor that still finds a
    # handful is the same lie as a fully dead one, and "could not check" is
    # exit 2, never the violation code.
    require_scan_floor(len(produced), 23, "producer artifact_type values (47 on 2026-08-02)")
    require_scan_floor(len(consumed), 2, "consumer artifact_type values (4 on 2026-08-02)")

    enum_cases, enum_path = _enum_cases(sw)
    dead_cases = sorted(enum_cases - produced) if enum_cases else []

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

    if enum_cases:
        print(f"note — Swift ArtifactType declares {len(enum_cases)} case(s); "
              f"the server writes {len(produced)}.")

    if dead_cases:
        print(f"\nFAIL: {len(dead_cases)} ArtifactType case(s) that NO server path writes")
        print(f"      in {enum_path}:\n")
        for c in dead_cases:
            print(f'  case {c}')
        print("\nAn enum case naming an artifact type nothing produces is a claim the\n"
              "backend does not support. Either the producer was never written, or the\n"
              "case is dead and should go.")
        return 1

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
