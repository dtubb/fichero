"""Names is not looked for on a page read too uncertainly, and the run says so (#5694), tested to the spec:
`source.onboard.auto.blank-pages-not-read` (docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: the overnight MCP walk (run 285cd81c): spaCy found 741 people, 327 places and 135 organisations in Kraken
text read at ~70% CER, with no warning. Names in text that poor are noise.
"""

from __future__ import annotations

import asyncio

from fichero_server.models import Segment
from fichero_server.llm.working_lines import write_readings
from fichero_server.recipes import runner
from tests.unit.training.test_kraken_training_set import _page


NAMES = {"steps": ["names"], "job": "find-names-tag-words", "card": "workflow", "workflow": "w", "workflow_id": "w",
         "provider_override": None, "model_override": None, "takes": ["text"], "gives": ["entities"]}


def _read(db, page, sure: float) -> None:
    """The page's lines read by a machine as sure as `sure`."""
    lines = [s for s in db.query(Segment, document_id=page.id) if s.kind == "line" and not s.deleted_at]
    assert lines
    write_readings(db, document_id=page.id, readings=[(s.id, "una línea", sure) for s in lines],
                   artifact_id=None, run_id="read-1")


def test_names_skips_a_page_read_too_uncertainly_and_says_why(db, tmp_path, monkeypatch):
    """source.job.names-warn-on-unreadable: Find Names skips a too-uncertain page and the step says which and why."""
    from fichero_server.models import DocType, Document
    from fichero_server.recipes.run_view import summary

    folder = Document(name="CACIQUES", doc_type=DocType.folder)
    db.save(folder)
    poor, good = _page(db, tmp_path, "1_Hoja", folder, read_by=None), _page(db, tmp_path, "2_Hoja", folder,
                                                                            read_by=None)
    from fichero_server.actions.registry import registry
    from tests.unit.training.test_kraken_training_set import BOOT, PAGE

    for page in (poor, good):
        registry.invoke(db, "format.import", {"document_id": page.id, "path": str(PAGE)}, BOOT)
    _read(db, poor, 0.42)
    _read(db, good, 0.93)
    assert round(runner.reading_confidence(db, poor.id), 2) == 0.42

    ran_on = []
    monkeypatch.setattr(runner, "_run_workflow",
                        lambda db_, card, documents, parent, adopt=None: ran_on.extend(documents) or ("thread", "done", None))
    job_id = runner.enqueue(db, {"runs": [NAMES], "skipped": []}, documents=[poor.id, good.id], started_by="owner")
    _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    (step,) = runner.run(db, subject)["steps"]

    assert set(ran_on) == {good.id}
    (left,) = step["left_out"]
    assert left["page_id"] == poor.id and "too uncertain to find names" in left["why"] and "42%" in left["why"]
    said = asyncio.run(summary(db, job_id)).lines
    assert "Names not looked for on 1 page: their reading is too uncertain" in said, said


def test_a_page_with_no_certainty_from_its_reader_is_not_held_back(db, tmp_path):
    from fichero_server.models import DocType, Document

    folder = Document(name="F", doc_type=DocType.folder)
    db.save(folder)
    page = _page(db, tmp_path, "1_Hoja", folder, read_by=None)
    assert runner.reading_confidence(db, page.id) is None
    assert runner.too_uncertain_for_names(db, [page.id]) == []
