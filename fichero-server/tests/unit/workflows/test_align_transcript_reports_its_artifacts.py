"""#4890: the align_transcript TOOL's artifacts reach the run's broadcast.

The run boundary (`completion.finalize_run_documents`) emits `artifact.updated` for
the ids `collect_created_artifact_ids` finds, and that collector reads ONE key:
`artifacts`. This tool already returned each `artifact_id` inside `documents` — under
a name the collector does not look at — so its aligned artifacts landed silently and
an overlay stayed stale. The fix is the key, not a second emit: the broadcast belongs
at the boundary that already fires it.
"""

from __future__ import annotations

from fichero_server.workflows.completion import collect_created_artifact_ids


def _tool_result(artifact_ids: list[str]) -> dict:
    """The tool's return shape, as `align_transcript` builds it."""
    documents = [
        {"doc_id": f"doc-{n}", "artifact_id": artifact_id}
        for n, artifact_id in enumerate(artifact_ids)
    ]
    return {
        "documents": documents,
        "aligned_count": len(documents),
        "skipped_count": 0,
        "artifacts": [entry["artifact_id"] for entry in documents],
    }


def test_the_collector_finds_what_the_tool_aligned():
    state = {"outputs": {"align": _tool_result(["art-1", "art-2"])}}

    assert collect_created_artifact_ids(state) == {"art-1", "art-2"}


def test_the_ids_inside_documents_alone_are_invisible_to_the_collector():
    """Why the key was needed at all. This is the OLD shape, and it proves the
    collector cannot see through it — so a test that only checked `documents` would
    have passed while the overlay stayed stale."""
    old_shape = {"documents": [{"doc_id": "doc-0", "artifact_id": "art-1"}]}

    assert collect_created_artifact_ids({"outputs": {"align": old_shape}}) == set()


def test_a_run_that_aligned_nothing_broadcasts_nothing():
    """Skipped pages (no baselines, no transcript, or a line/baseline mismatch) write
    no artifact. An empty list must stay empty rather than becoming an event for a
    write that did not happen."""
    nothing = {"documents": [], "aligned_count": 0, "skipped_count": 3, "artifacts": []}

    assert collect_created_artifact_ids({"outputs": {"align": nothing}}) == set()


def test_the_real_tool_builds_the_key_from_its_own_documents():
    """Pins the tool's source rather than my copy of its shape: the two must agree,
    or this file tests a fiction."""
    import inspect

    from fichero_server.workflows.tools import align_transcript

    source = inspect.getsource(align_transcript)
    assert '"artifacts": [entry["artifact_id"] for entry in documents]' in source, (
        "align_transcript no longer reports its artifacts under the key "
        "collect_created_artifact_ids reads"
    )
