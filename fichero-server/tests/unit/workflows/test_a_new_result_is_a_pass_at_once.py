"""#5222 part 2: a result with boxes becomes its own pass in the run that made it.

`source.convert.a-new-result-is-a-pass-at-once` and `source.convert.a-result-that-cannot-convert-is-kept`
(docs/contributor_manual/specs/source/segments-and-geometry.md). Before this, every tool saved its
boxes on an artifact only, and they became a pass at the next open of the library or at a person's
first edit; a page the maintainer had just run Apple Vision on showed legacy artifact geometry and
"No Reading Order" (2026-09-28). What breaks without these tests: a producer that goes back to
leaving its boxes unconverted, or a conversion failure that takes the tool's result down with it.

Driven through the REAL `save_artifact` on a real library database (only the database lookup is
pointed at the test's), because that is the seam every vision and LLM tool saves through.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import ActionAudit, Artifact, DocType, Document, FileType, Segment, SegmentPass, Status


def _page(db, name="folio 1"):
    doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image, path=f"/p/{name}.jpg",
                   status=Status.completed, metadata={"width": 2000, "height": 3000})
    db.save(doc)
    return doc


def _vision_result():
    return OCRGeometryResult(provider="apple_vision", text="In the year", boxes=[
        OCRGeometryBox(text="In the year", bbox=[0.1, 0.1, 0.5, 0.04], level="line"),
        OCRGeometryBox(text="of grace", bbox=[0.1, 0.2, 0.5, 0.04], level="line"),
    ])


def _save(db, doc, geometry, *, task_id="run-1"):
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.llm_base import save_artifact
    from fichero_server.workflows.tools.vision_base import VisionToolConfig

    tool_config = VisionToolConfig(
        artifact_type="transcription", update_page_content=True, trigger_embedding=False,
        supports_apple_vision=True, skip_if_artifact_exists=False,
    )
    with patch("fichero_server.db.db_manager.get_database", return_value=db):
        return asyncio.run(save_artifact(
            document_id=doc.id, file_path=None, content=geometry.text if geometry else "text",
            data=None, library_path="/tmp/test.fichero", llm_config=LLMConfig(provider="apple_vision", model="vision"),
            task_id=task_id, tool_config=tool_config, ocr_geometry=geometry,
        ))


def test_a_tools_result_with_boxes_is_its_own_pass_when_the_run_saves_it(db):
    doc = _page(db)
    artifact_id = _save(db, doc, _vision_result())

    passes = db.query(SegmentPass, document_id=doc.id)
    assert len(passes) == 1, "the result is a pass now, not at the next open"
    rows = [s for s in db.query(Segment, pass_id=passes[0].id) if s.deleted_at is None]
    assert len(rows) == 2, "a segment per box"
    assert db.get(Artifact, artifact_id).geometry_superseded_by_pass_id == passes[0].id

    audit = next(a for a in db.all(ActionAudit) if a.action_name == "segment.convert_and_edit")
    assert audit.actor == "system", "the engine's own work, not a person's"
    assert audit.run_id == "run-1", "tied to the run that made the result"


def test_a_result_without_boxes_makes_no_pass(db):
    doc = _page(db)
    _save(db, doc, None)
    assert db.query(SegmentPass, document_id=doc.id) == []


def test_a_rerun_adds_a_pass_beside_the_first_and_changes_neither(db):
    doc = _page(db)
    _save(db, doc, _vision_result(), task_id="run-1")
    first = db.query(SegmentPass, document_id=doc.id)[0]
    _save(db, doc, _vision_result(), task_id="run-2")
    passes = db.query(SegmentPass, document_id=doc.id)
    assert len(passes) == 2
    assert db.get(SegmentPass, first.id) == first, "the earlier pass is untouched"


def test_a_conversion_that_fails_keeps_the_result_and_the_run(db, caplog):
    """`source.convert.a-result-that-cannot-convert-is-kept`: never a reason to lose a result."""
    doc = _page(db)
    with patch(
        "fichero_server.maintenance.project_conversion._convert_one_page",
        side_effect=RuntimeError("the disk said no"),
    ):
        artifact_id = _save(db, doc, _vision_result())

    kept = db.get(Artifact, artifact_id)
    assert kept is not None and kept.ocr_geometry.boxes, "the result is saved with its boxes"
    assert kept.geometry_superseded_by_pass_id is None, "it waits for the next open"
    assert doc.id in db.documents_with_unconverted_geometry()
    assert any(
        r.levelname == "ERROR" and doc.id in r.getMessage() and "the disk said no" in r.getMessage()
        for r in caplog.records
    )


# --- `source.convert.no-producer-writes-boxes-alone`: the guard ----------------------------------

import ast  # noqa: E402
from pathlib import Path  # noqa: E402

ENGINE = Path(__file__).resolve().parents[3] / "src" / "fichero_server"

#: Places that write an artifact's boxes and rightly do NOT hand them to the conversion. Each says
#: why; anything else that writes boxes without `convert_new_results` fails the guard.
NOT_A_PRODUCER = {
    "api/routes/document/segment_conversion.py": "the conversion itself, restoring a kept block on undo",
    "api/routes/document/artifacts.py::_edit_regions_impl":
        "a PERSON's edit of an unconverted result's boxes (the older editor route), not a machine's result",
}


def _writes_boxes(node: ast.AST) -> bool:
    """`Artifact(..., ocr_geometry=<not None>)` or `<x>.ocr_geometry = ...`."""
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Artifact":
        return any(
            kw.arg == "ocr_geometry" and not (isinstance(kw.value, ast.Constant) and kw.value.value is None)
            for kw in node.keywords
        )
    if isinstance(node, ast.Assign):
        return any(isinstance(t, ast.Attribute) and t.attr == "ocr_geometry" for t in node.targets)
    return False


def _calls(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(n, ast.Call) and (getattr(n.func, "id", None) == name or getattr(n.func, "attr", None) == name)
        for n in ast.walk(node)
    )


def unconverted_box_writers(root: Path = ENGINE, allowed: dict = NOT_A_PRODUCER) -> list[str]:
    """Every function that writes boxes but never calls `convert_new_results`, as `path::function:line`.

    ponytail: per function, by name. A builder that RETURNS an unsaved artifact for its caller to
    save (`align_and_build_artifact`) is not followed to the caller; its two callers convert, and
    `test_an_aligned_transcript_is_its_own_pass` pins one. Follow builders if a third appears.
    """
    offenders = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if f"{rel}::{fn.name}" in allowed:
                continue
            writes = [n for n in ast.walk(fn) if _writes_boxes(n)]
            if not writes:
                continue
            saves = _calls(fn, "save") or _calls(fn, "save_many")
            if saves and not _calls(fn, "convert_new_results"):
                offenders.append(f"{rel}::{fn.name}:{writes[0].lineno}")
    return offenders


def test_no_producer_saves_boxes_without_converting_them():
    offenders = unconverted_box_writers()
    assert not offenders, (
        "These save a result's boxes without making it a pass (#5222 part 2). Call "
        "maintenance.project_conversion.convert_new_results after the save, or list the place in "
        f"NOT_A_PRODUCER with its reason: {offenders}"
    )


def test_the_guard_sees_a_producer_that_skips_the_conversion(tmp_path):
    (tmp_path / "tool.py").write_text(
        "def run(db, doc_id, geometry):\n"
        "    db.save(Artifact(document_id=doc_id, ocr_geometry=geometry))\n"
    )
    (tmp_path / "good.py").write_text(
        "def run(db, doc_id, geometry):\n"
        "    db.save(Artifact(document_id=doc_id, ocr_geometry=geometry))\n"
        "    convert_new_results(db, doc_id)\n"
    )
    (tmp_path / "plain.py").write_text(
        "def run(db, doc_id):\n"
        "    db.save(Artifact(document_id=doc_id, ocr_geometry=None))\n"
    )
    assert unconverted_box_writers(tmp_path, {}) == ["tool.py::run:2"]
    assert unconverted_box_writers(tmp_path, {"tool.py": "a reason"}) == []


def test_the_guard_reads_the_real_producers():
    """Not vacuous: the scan finds the producers this was built for, and each one converts."""
    found = []
    for rel in ("workflows/tools/llm_base.py", "workflows/tools/merge_geometry.py",
                "importers/ingest.py", "workflows/tools/vision_base.py"):
        tree = ast.parse((ENGINE / rel).read_text(encoding="utf-8"))
        if any(_writes_boxes(n) for n in ast.walk(tree)):
            found.append(rel)
    assert len(found) == 4


def test_an_aligned_transcript_is_its_own_pass(db):
    """The on-demand alignment route saves the artifact its builder made; it converts it too.
    The alignment itself is stubbed (its own tests cover it): what is pinned is the save."""
    from fichero_server.api.routes.document import artifacts as artifacts_route

    doc = _page(db)
    regions = Artifact(document_id=doc.id, artifact_type="regions", provider="kraken")
    db.save(regions)
    aligned = Artifact(document_id=doc.id, artifact_type="aligned_transcript", provider="kraken",
                       content="In the year\nof grace", ocr_geometry=_vision_result())
    geometry = _vision_result()
    geometry.metadata = {}
    with (
        patch.object(artifacts_route, "resolve_transcript", return_value="In the year\nof grace"),
        patch.object(artifacts_route, "align_and_build_artifact", return_value=(geometry, aligned)),
    ):
        asyncio.run(artifacts_route.align_transcript_to_regions(regions.id, db=db))

    passes = db.query(SegmentPass, document_id=doc.id)
    assert len(passes) == 1
    assert db.get(Artifact, aligned.id).geometry_superseded_by_pass_id == passes[0].id


def test_each_converted_box_gets_its_words_as_a_reading_with_the_machines_maker(db):
    """`source.convert.words-move-with-the-boxes` (the words half): the old block is no longer the
    only home of a line's text. Each box with words becomes a transcription reading on its segment,
    made by the machine that read it, not by whoever's library the engine was converting."""
    from fichero_server.models import ContentRepresentation
    from fichero_server.models.knowledge import ProvenanceKind

    doc = _page(db)
    _save(db, doc, _vision_result())
    pass_row = db.query(SegmentPass, document_id=doc.id)[0]
    rows = [s for s in db.query(Segment, pass_id=pass_row.id) if s.deleted_at is None]
    readings = {r.segment_id: r for r in db.query(ContentRepresentation, document_id=doc.id)}
    assert sorted(readings[s.id].content for s in rows) == ["In the year", "of grace"]
    assert {r.kind for r in readings.values()} == {"transcription"}
    assert all(r.provenance_kind != ProvenanceKind.human for r in readings.values())
