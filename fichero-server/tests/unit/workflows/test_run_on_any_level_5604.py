"""Run a workflow at any level, and its results attach at that level (#5604).

Spec: `docs/contributor_manual/specs/source/source-model.md`, "Extracted data, integrated (review
2026-10-07)":

- `source.extract.run-on-any-level`: a run's selection can be a set of segments at any level
  (regions, lines, words, signs) or a group of documents; the server resolves it, and each step is
  given what it needs for that level: the segment's picture cut to it, and its current reading.
- `source.extract.outputs-attach-at-their-level`: a result made from a segment attaches to that
  segment (a reading), never to the page.

Driven through the public surface: real runs started with `POST /api/workflow-execution/execute`,
read back through the segment's readings route and the run's status. Only the model call is a stub
(a cloud vision model answering from memory, recording the size of each picture it was shown).
"""
# ruff: noqa: F811 -- pytest fixtures imported from test_runs_are_jobs are named as test arguments
from __future__ import annotations

import base64
import io
import threading

import pytest

from fichero_server.models import DocType, Document, FileType, Status, Workflow
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import Segment, bbox_and_tile_from_anchor
from tests.unit.jobs.test_runs_are_jobs import _status, _wait_for, no_embedding_model  # noqa: F401

pytestmark = pytest.mark.source_model

PAGE_TEXT = "Texto de la pagina entera, como estaba."
LINE_READ = "vecino de la ciudad"
WIDTH, HEIGHT = 400, 200


class SeeingModel:
    """A cloud vision model that answers from memory and remembers the size of each picture."""

    def __init__(self) -> None:
        self.sizes: list[tuple[int, int]] = []
        self.lock = threading.Lock()

    async def __call__(self, images, prompt, config, **kwargs):
        from PIL import Image

        for uri in images:
            payload = base64.b64decode(uri.split(",", 1)[1])
            with Image.open(io.BytesIO(payload)) as seen, self.lock:
                self.sizes.append(seen.size)
        return LINE_READ


@pytest.fixture
def seeing(monkeypatch):
    import fichero_server.llm as llm
    from fichero_server.workflows import validation

    model = SeeingModel()
    monkeypatch.setattr(llm, "vision", model)
    monkeypatch.setattr(validation, "validate_workflow_llm_preflight", lambda *a, **k: [])
    return model


def _image(db, name: str, size=(WIDTH, HEIGHT)):
    from PIL import Image

    path = db.path.parent / name
    Image.new("RGB", size, (255, 255, 255)).save(path)
    return path


@pytest.fixture
def page(db):
    doc = Document(name="folio-1.png", doc_type=DocType.file, file_type=FileType.image,
                   path=str(_image(db, "folio-1.png")), status=Status.completed, page_content=PAGE_TEXT)
    db.save(doc)
    return doc


def _segment(db, doc, kind: str, rect) -> Segment:
    anchor = SourceAnchor(document_id=doc.id, rect=list(rect))
    x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
    row = Segment(
        document_id=doc.id, pass_id=f"pass-{doc.id}", kind=kind, anchor=anchor,
        bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h, tile=tile, doc_kind=f"{doc.id}:{kind}",
        provenance_kind=ProvenanceKind.workflow,
    )
    db.save(row)
    return row


def _workflow(db, wf_id: str, tool: str, config=None) -> Workflow:
    wf = Workflow(
        id=wf_id, name=f"{tool} on a selection", provider="openai", model="gpt-5",
        nodes=[
            {"id": "files-source", "tool": "files", "label": "Files", "inputs": {}, "config": {}},
            {"id": "step", "tool": tool, "label": tool,
             "inputs": {"files": "$.nodes.files-source.files", "documents": "$.nodes.files-source.documents"},
             "config": {"vision_mode": "llm", **(config or {})}},
        ],
        edges=[{"id": "e1", "source": "files-source", "target": "step", "source_port": "files",
                "target_port": "files"}],
    )
    db.save(wf)
    return wf


def _execute(client, workflow, kind: str, ids: list[str]):
    return client.post("/api/workflow-execution/execute", json={
        "workflow_id": workflow.id, "selection": {"kind": kind, "ids": ids}, "skip_cache": True})


def _run(client, workflow, kind: str, ids: list[str]) -> str:
    r = _execute(client, workflow, kind, ids)
    assert r.status_code == 202, r.text
    thread_id = r.json()["thread_id"]
    assert _wait_for(lambda: _status(client, thread_id) in ("completed", "failed"))
    assert _status(client, thread_id) == "completed", client.get(
        f"/api/workflow-execution/threads/{thread_id}/status").json().get("error")
    return thread_id


def _readings(client, segment_id: str, kind: str):
    r = client.get(f"/api/segments/{segment_id}/readings", params={"kind": kind})
    assert r.status_code == 200, r.text
    return [item for item in r.json()["items"] if not item["provisional"]]


# ── source.extract.run-on-any-level + outputs-attach-at-their-level ─────────────


def test_a_read_of_one_line_is_a_reading_on_that_line_and_the_page_text_is_untouched(
    client, db, page, seeing
):
    line = _segment(db, page, "line", (0.0, 0.25, 1.0, 0.25))
    other = _segment(db, page, "line", (0.0, 0.6, 1.0, 0.25))
    workflow = _workflow(db, "wf-read-a-line", "transcribe", {"update_page_content": True})

    _run(client, workflow, "segments", [line.id])

    readings = _readings(client, line.id, "transcription")
    assert [r["content"] for r in readings] == [LINE_READ], readings
    assert readings[0]["segment_id"] == line.id and readings[0]["provenance_kind"] == "workflow"
    assert _readings(client, other.id, "transcription") == [], "the line beside it was given the read"
    live = client.get(f"/api/documents/{page.id}").json()
    assert live["page_content"] == PAGE_TEXT, "a line's read was written over the page's text"
    # The model was shown the line, not the page: 400 x 50 pixels.
    assert seeing.sizes == [(400, 50)]


def test_a_word_and_a_sign_are_each_read_from_their_own_crop(client, db, page, seeing):
    word = _segment(db, page, "word", (0.1, 0.3, 0.25, 0.1))     # 100 x 20
    sign = _segment(db, page, "sign", (0.5, 0.5, 0.05, 0.2))     # 20 x 40
    workflow = _workflow(db, "wf-read-signs", "transcribe")

    _run(client, workflow, "segments", [word.id, sign.id])

    assert sorted(seeing.sizes) == sorted([(100, 20), (20, 40)]), seeing.sizes
    assert [r["content"] for r in _readings(client, word.id, "transcription")] == [LINE_READ]
    assert [r["content"] for r in _readings(client, sign.id, "transcription")] == [LINE_READ]
    assert client.get(f"/api/documents/{page.id}").json()["page_content"] == PAGE_TEXT


def test_a_description_of_a_word_is_a_description_reading_on_the_word(client, db, page, seeing):
    word = _segment(db, page, "word", (0.1, 0.3, 0.25, 0.1))
    workflow = _workflow(db, "wf-describe-a-word", "describe")

    _run(client, workflow, "segments", [word.id])

    assert [r["content"] for r in _readings(client, word.id, "description")] == [LINE_READ]
    page_readings = client.get(f"/api/content-representations/document/{page.id}").json()["items"]
    assert not [r for r in page_readings if r["segment_id"] is None], "the word's description went onto the page"


def test_a_segment_is_given_its_current_reading(db, page, test_package):
    from fichero_server.llm.working_lines import write_readings
    from fichero_server.workflows.selection import SEGMENT_TARGET_KEY
    from fichero_server.workflows.tools.sources import segment_work_units

    line = _segment(db, page, "line", (0.0, 0.25, 1.0, 0.25))
    write_readings(db, document_id=page.id, readings=[(line.id, "lo que dice la linea")], artifact_id=None,
                   run_id="earlier-run", library_path=str(test_package))

    files, documents = segment_work_units(db, [line.id], str(test_package))

    assert documents[0]["id"] == page.id
    assert documents[0][SEGMENT_TARGET_KEY] == {"segment_id": line.id, "level": "line",
                                                "text": "lo que dice la linea"}
    assert documents[0]["page_content"] == "lo que dice la linea"
    from PIL import Image

    with Image.open(files[0]) as picture:
        assert picture.size == (400, 50)


def test_a_group_runs_on_its_member_pages_in_the_groups_order(client, db, seeing):
    from fichero_server.api.routes.document.documents import DocumentGroupParams, group_documents_impl

    pages = []
    for name in ("a.png", "b.png", "c.png"):
        doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image,
                       path=str(_image(db, name, (16, 16))), status=Status.completed)
        db.save(doc)
        pages.append(doc)
    # Given out of name order: the group is read in ITS order, never by name.
    order = [pages[2].id, pages[0].id, pages[1].id]
    group = group_documents_impl(db, DocumentGroupParams(name="Caso 7", child_ids=order))
    workflow = _workflow(db, "wf-read-a-group", "transcribe", {"update_page_content": True})

    thread_id = _run(client, workflow, "group", [group.id])

    state = client.get(f"/api/workflow-execution/threads/{thread_id}/status").json()["current_state"]
    resolved = [doc["id"] for doc in state["outputs"]["files-source"]["documents"]]
    assert resolved == order
    assert len(seeing.sizes) == 3
    for doc_id in order:
        assert client.get(f"/api/documents/{doc_id}").json()["page_content"] == LINE_READ


# ── refusals, in words ──────────────────────────────────────────────────────────


def test_a_page_only_step_on_a_line_is_refused_in_words(client, db, page, seeing):
    line = _segment(db, page, "line", (0.0, 0.25, 1.0, 0.25))
    # Classify reads a picture too, but declares its answer an attribute of the page: not wired.
    workflow = _workflow(db, "wf-classify-a-line", "classify")

    r = _execute(client, workflow, "segments", [line.id])

    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Classify runs on pages, not on a line"
    assert seeing.sizes == [], "a refused run still read something"
    assert client.get(f"/api/documents/{page.id}").json()["page_content"] == PAGE_TEXT


def test_an_unknown_segment_is_refused(client, db, page, seeing):
    workflow = _workflow(db, "wf-read-nothing", "transcribe")

    r = _execute(client, workflow, "segments", ["no-such-segment"])

    assert r.status_code == 400
    assert "no-such-segment is not in this project" in r.json()["detail"]


def test_a_group_selection_that_names_a_page_is_refused(client, db, page, seeing):
    workflow = _workflow(db, "wf-group-of-one-page", "transcribe")

    r = _execute(client, workflow, "group", [page.id])

    assert r.status_code == 400
    assert r.json()["detail"] == f"{page.id} is not a group of documents in this project"


def test_a_group_is_one_container():
    from pydantic import ValidationError

    from fichero_server.workflows.selection import WorkflowSelection

    with pytest.raises(ValidationError, match="names a single container"):
        WorkflowSelection(kind="group", ids=["g1", "g2"])


def test_only_wired_readers_and_the_files_source_run_on_segments():
    from fichero_server.workflows.tool_outputs import SEGMENT_READERS, TOOL_OUTPUTS, runs_on_segments

    for tool in SEGMENT_READERS:
        declaration = TOOL_OUTPUTS[tool]
        assert declaration.anchors_at == "segment", tool
        assert declaration.writes & {"reading", "page_text"}, tool
    assert runs_on_segments("files") and runs_on_segments("selection")
    assert not runs_on_segments("translate") and not runs_on_segments("collection")
    assert not runs_on_segments("sub_workflow")
