"""Seam category — constructions that still name a RETIRED geometry field.

Every bbox in this codebase has been consolidated onto `SourceAnchor` /
`NodeRegion` (2026-08-20 .. 2026-08-22). The retired names are gone from the
models. They are NOT gone from the language: these models are configured
`extra="allow"`, so a stale keyword is accepted at construction, stored as an
inert attribute, and only causes trouble somewhere else entirely.

MEASURED, TWICE, IN ONE EVENING:

* `Annotation(..., bbox=[0.4, 0.4, 0.2, 0.2])` in a crop test. `crop_image`
  reads `ann.anchor`, saw None, returned None, and the test failed on
  `assert png is not None` — a symptom three steps from the cause.
* `Annotation(..., bbox=[...])` in a library-columns test. The extra field
  reached the writer and DuckDB raised
  `Table "annotations" does not have a column with name "bbox"` from inside
  an unrelated assertion about column roll-ups.

Both took a full unit sweep to surface and a manual bisect to attribute. This
scan finds them in about a second, and names the field and the line.

THE RULE: a retired geometry field name may not appear as a keyword argument
to a model that used to declare it, and `source_bbox` may not appear at all —
that name was retired everywhere, with no successor spelling.

METHOD. AST over `src/fichero_server` and `tests`, no text matching:

1. every `ast.Call` keyword named `source_bbox` is flagged wherever it occurs;
2. a keyword named `bbox` is flagged ONLY when the callee is one of the models
   that retired it;
3. every ATTRIBUTE READ of a retired name — `claim.source_bbox` — is flagged.

Pass (3) was added after this scan passed clean while
`test_claim_writer_preserves_source_bbox` was still failing: it asserted on
`claim.source_bbox`, which is a read, not a construction. A guardrail that
only watches the write side misses half the callers, and this one proved it
by missing one on its first day.

WHAT IS DELIBERATELY NOT FLAGGED: the STRING `"source_bbox"` as a dict key.
That is the extractor's LLM payload vocabulary — `item.get("source_bbox")` in
`extractors.py` is current, correct code that wraps the raw rect into a
`SourceAnchor` at the boundary. Flagging the payload spelling would force a
rename of the model's wire contract to satisfy a test about our own storage,
which is the tail wagging the dog.

Scoping (2) to those callees is the whole reason this is precise rather than
noisy: `bbox` is still the correct, current field name on `OCRGeometryBox`,
`EvidentialPlace` (a GEOGRAPHIC extent, not an image region), and the docling
loader's table boxes. A blanket ban on the word would flag 30+ correct lines
and be switched off within a week.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: Models that retired `bbox`. A keyword `bbox=` aimed at one of these is a
#: stale caller; aimed at anything else it is very likely still correct.
RETIRED_BBOX_CALLEES = {
    "Annotation",
    "ColumnAnnotation",
    "ContentSourceAnchor",  # deleted outright; absorbed into SourceAnchor
}

#: Retired with no successor spelling, so any occurrence is stale.
ALWAYS_RETIRED = {"source_bbox"}

ROOT = Path(__file__).resolve().parents[3]
SCAN_ROOTS = (ROOT / "src" / "fichero_server", ROOT / "tests")


def _callee_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _offenders_in(tree: ast.AST, path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        # Reads: `claim.source_bbox`. Note this is an ast.Attribute, NOT an
        # ast.Constant — the string "source_bbox" used as a payload dict key
        # is untouched on purpose.
        if isinstance(node, ast.Attribute) and node.attr in ALWAYS_RETIRED:
            found.append(f"{path}:{node.lineno}: read of .{node.attr}")
            continue
        if not isinstance(node, ast.Call):
            continue
        callee = _callee_name(node)
        for keyword in node.keywords:
            if keyword.arg is None:
                continue
            if keyword.arg in ALWAYS_RETIRED:
                found.append(f"{path}:{node.lineno}: {callee}(..., {keyword.arg}=)")
            elif keyword.arg == "bbox" and callee in RETIRED_BBOX_CALLEES:
                found.append(f"{path}:{node.lineno}: {callee}(..., bbox=)")
    return found


def _scan(paths) -> list[str]:
    offenders: list[str] = []
    for root in paths:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                # A file we cannot parse is reported, never skipped silently —
                # a guardrail that quietly ignores input is not a guardrail.
                offenders.append(f"{path}: could not be parsed")
                continue
            offenders.extend(_offenders_in(tree, path))
    return offenders


def test_no_construction_names_a_retired_geometry_field():
    offenders = _scan(SCAN_ROOTS)
    assert not offenders, (
        "These pass a retired geometry field. The models are extra=\"allow\", so "
        "this does NOT raise at construction — it fails later and elsewhere:\n  "
        + "\n  ".join(offenders)
    )


class TestTheDetectorActuallyFires:
    """A guardrail nobody has seen fail is a guardrail nobody knows works."""

    @pytest.mark.parametrize(
        "source",
        [
            "Annotation(document_id='d', bbox=[0, 0, 1, 1])",
            "ColumnAnnotation(id='a', bbox=[0, 0, 1, 1])",
            "KnowledgeClaim(text='t', source_bbox=[0, 0, 1, 1])",
            "models.Annotation(bbox=[0, 0, 1, 1])",
            # The read side — the form that slipped past the first version.
            "assert claim.source_bbox == [0, 0, 1, 1]",
            "value = support.source_bbox",
        ],
    )
    def test_it_catches_a_stale_construction(self, source):
        assert _offenders_in(ast.parse(source), Path("sample.py"))

    @pytest.mark.parametrize(
        "source",
        [
            # `bbox` is the CURRENT, correct field on these.
            "OCRGeometryBox(text='a', bbox=[0.1, 0.1, 0.2, 0.05])",
            "EvidentialPlace(name='x', bbox=[-77.2, 2.1, -76.2, 3.0])",
            # The successor spellings must never be flagged.
            "Annotation(document_id='d', anchor=SourceAnchor(rect=[0, 0, 1, 1]))",
            "Document(name='p', region_in_parent=NodeRegion(rect=[0, 0, 1, 1]))",
            # The extractor's LLM payload vocabulary, which is current code.
            'raw = item.get("source_bbox")',
            'payload = {"source_bbox": [0, 0, 1, 1]}',
        ],
    )
    def test_it_leaves_correct_code_alone(self, source):
        assert not _offenders_in(ast.parse(source), Path("sample.py"))
