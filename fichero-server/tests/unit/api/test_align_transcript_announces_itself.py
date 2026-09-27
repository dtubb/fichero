"""#4890's other half: an aligned artifact says so on the change stream.

The maintainer ran Kraken, it produced boxes, and they did not appear until he
clicked the item. The cause was that saving an artifact emitted no event and the
run's only event rode on a document STATUS transition. The run boundary was fixed
(`completion.finalize_run_documents`); this route was not, and it cannot be covered
there because there is no run — it aligns one page on demand.

What these tests pin is the engine half only. The behaviour stays [BROKEN] until the
maintainer sees the boxes appear: an event existing is not an overlay redrawing.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fichero_server.api.routes.document import artifacts as artifacts_route


def _regions(document_id: str = "doc-1") -> MagicMock:
    row = MagicMock()
    row.id = "regions-1"
    row.document_id = document_id
    return row


def _aligned_artifact(document_id: str = "doc-1") -> MagicMock:
    made = MagicMock()
    made.id = "aligned-1"
    made.document_id = document_id
    return made


async def _run(*, artifact) -> list[dict]:
    """Call the route with alignment stubbed, and collect what it broadcast."""
    db = MagicMock()
    db.get.return_value = _regions()
    db.path = "/tmp/lib.fichero/library.duckdb"
    emitted: list[dict] = []

    aligned = MagicMock()
    aligned.metadata = {}

    with (
        patch.object(artifacts_route, "resolve_transcript", return_value="a line\nanother"),
        patch.object(
            artifacts_route, "align_and_build_artifact", return_value=(aligned, artifact)
        ),
        patch.object(artifacts_route, "_artifact_response", return_value=None),
        patch(
            "fichero_server.api.change_stream.emit_change",
            lambda library_path, **kwargs: emitted.append(dict(kwargs, library=library_path)),
        ),
    ):
        await artifacts_route.align_transcript_to_regions("regions-1", db=db)
    return emitted


async def test_an_aligned_artifact_broadcasts_itself_and_its_page():
    emitted = await _run(artifact=_aligned_artifact())

    assert len(emitted) == 1, "exactly one event per alignment"
    event = emitted[0]
    assert event["type"] == "artifact.updated"
    # Both ids, because a subscriber redrawing an overlay needs to know WHICH page
    # as well as which artifact.
    assert event["artifact_ids"] == ["aligned-1"]
    assert event["document_ids"] == ["doc-1"]


async def test_the_broadcast_comes_AFTER_the_row_is_saved():
    """Order matters, and this is the one thing a mock can prove that the guard cannot.

    A subscriber reacts by refetching. If the event went out before the save, it would
    read the row as it was and redraw the stale overlay — the very symptom #4890 is
    about, reintroduced by getting the order wrong.

    This also stands in for "fires although no status changed": nothing in this route
    reads or writes a document's status, and the event still goes out.
    """
    order: list[str] = []
    db = MagicMock()
    db.get.return_value = _regions()
    db.path = "/tmp/lib.fichero/library.duckdb"
    db.save.side_effect = lambda row: order.append(f"save:{row.id}")

    aligned = MagicMock()
    aligned.metadata = {}

    with (
        patch.object(artifacts_route, "resolve_transcript", return_value="a line"),
        patch.object(
            artifacts_route,
            "align_and_build_artifact",
            return_value=(aligned, _aligned_artifact()),
        ),
        patch.object(artifacts_route, "_artifact_response", return_value=None),
        patch(
            "fichero_server.api.change_stream.emit_change",
            lambda library_path, **kwargs: order.append(f"emit:{kwargs['type']}"),
        ),
    ):
        await artifacts_route.align_transcript_to_regions("regions-1", db=db)

    assert order == ["save:aligned-1", "emit:artifact.updated"], order


async def test_nothing_is_broadcast_when_nothing_was_aligned():
    """A declined alignment (line and baseline counts disagree) writes no artifact,
    so it must not claim one changed. An event for a write that did not happen would
    make a subscriber refetch and show the same thing, which teaches people to
    distrust the stream."""
    assert await _run(artifact=None) == []
