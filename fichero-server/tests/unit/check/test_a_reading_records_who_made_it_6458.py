"""`source.editor.a-reading-records-who-made-it` (#6458): a reading records its maker on the row itself.

After a tie, the tied line reading carries the page reader's model and `tie-text-to-lines` as its tool; a step's line
reading (`working_lines.write_readings`) carries the model of the artifact it came from. So a line's versions are labelled
"reader · model · level · when" from the row alone, with no join to the artifact.
"""
from __future__ import annotations

from fichero_server.llm.working_lines import write_readings
from fichero_server.models import Artifact, ContentRepresentation
from tests.unit.check.test_tie_text_to_lines import _run, _tied, page, reader  # noqa: F401  (fixtures)
from tests.unit.training.test_kraken_training_set import TEACHER


def test_a_tied_line_records_the_page_readers_model_and_the_tie_as_its_tool(client, db, page, reader):  # noqa: F811
    """WHY: the reading's reader was found by a join to the artifact; the row said only which artifact it derived from."""
    _run(client, db, page)
    made = [db.get(ContentRepresentation, r.id) for _row, r in _tied(db, page) if r]  # the stored rows, not the API view
    assert len(made) > 5
    assert {r.producer_model for r in made} == {f"openrouter/{TEACHER}"}
    assert {r.producer_tool for r in made} == {"tie-text-to-lines"}


def test_a_step_line_reading_records_the_model_of_its_artifact_and_its_tool(db, page):  # noqa: F811
    """WHY: after Normalise the line's regularised reading must say who made it without a second request."""
    from fichero_server.api.routes.document.segment_readings import ordered_lines

    line = ordered_lines(db, page["kraken"].id)[0]
    artifact = Artifact(document_id=page["doc"].id, artifact_type="transcription", content="uno", model="claude-sonnet-5-5",
                        provider="anthropic")
    db.save(artifact)
    (made,) = write_readings(db, document_id=page["doc"].id, readings=[(line.id, "uno")], artifact_id=artifact.id,
                             run_id="run-1", level="regularised", tool="normalise")
    row = db.get(ContentRepresentation, made)
    assert (row.producer_model, row.producer_tool, row.producer_run_id, row.level) == (
        "anthropic/claude-sonnet-5-5", "normalise", "run-1", "regularised")


def test_a_workflow_steps_reading_records_the_steps_job_id_not_its_artifact_type(db):
    """WHY: `producer_tool` is the step's job id (`normalise`), so the Levels row can name the step; the artifact type
    ("translation", "regularised") names a kind of output, and recording it would pass a test that only checks non-empty."""
    from fichero_server.workflows import node_context
    from fichero_server.models import Document

    doc = Document(name="page.png", path="/tmp/page.png")
    db.save(doc)
    artifact = Artifact(document_id=doc.id, artifact_type="regularised", content="uno", model="m", provider="p")
    db.save(artifact)
    node_context.set_current_node("node-3", "Normalise", "wf-1", tool="normalise")
    try:
        (made,) = write_readings(db, document_id=doc.id, readings=[(None, "uno")], artifact_id=artifact.id, run_id="r1",
                                 kind="transcription", level="regularised")
    finally:
        node_context._current_node.set(None)
    row = db.get(ContentRepresentation, made)
    assert row.producer_tool == "normalise" != artifact.artifact_type
