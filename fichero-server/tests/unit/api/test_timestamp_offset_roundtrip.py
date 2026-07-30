"""End-to-end timezone contract for persisted timestamps (#4347).

These are deliberately *round-trip* tests, not conversion unit tests: the bug
was that a value written naive-local survived persistence and serialization
without an offset, so an ISO-8601 decoder read it as UTC and rendered a run that
just happened as "3 hours ago". Proving that cannot recur means asserting on the
JSON a client actually receives after a real write to a real DuckDB file.

Each test therefore checks two things the old code got wrong:

1. the serialized string carries a UTC offset (``+00:00`` / ``Z``), and
2. the instant it denotes is *now* — within a small window of the real clock,
   which is what fails by exactly the local offset if a naive local value is
   ever re-labelled as UTC.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fichero_server.core.timeutil import utc_now
from fichero_server.models import Artifact, Document
from fichero_server.workflows.activity import ActivityTracker
from fichero_server.workflows.activity_types import ActivityType

# A naive-local write mislabelled as UTC is wrong by the machine's own offset.
# Anywhere with a non-zero offset that is at least this large, the assertion
# below fails — which is the point. 5 minutes leaves room for a slow test box
# without tolerating a whole-hour timezone error.
_TOLERANCE = timedelta(minutes=5)


def _assert_offset_bearing_now(text: str, *, field: str) -> datetime:
    """Assert an ISO-8601 string is offset-bearing and denotes roughly now."""
    assert text, f"{field} was empty"
    assert text.endswith("+00:00") or text.endswith("Z"), (
        f"{field} carries no UTC offset: {text!r} — an offset-less ISO string is "
        "read as UTC by the client and shifts by the server's local offset"
    )
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    drift = abs(parsed - utc_now())
    assert drift < _TOLERANCE, (
        f"{field} denotes {parsed.isoformat()}, which is {drift} away from now — "
        "this is the naive-local-written / read-as-UTC shift"
    )
    return parsed


# ---------------------------------------------------------------------------
# Artifacts (the artifacts inspector surface from the report)
# ---------------------------------------------------------------------------


def test_artifact_created_via_api_reads_back_with_a_utc_offset(client, db) -> None:
    doc = Document(name="timestamp-round-trip.txt")
    db.save(doc)

    created = client.post(
        "/api/artifacts/",
        json={
            "document_id": doc.id,
            "artifact_type": "transcription",
            "content": "hello",
        },
    )
    assert created.status_code == 200, created.text
    _assert_offset_bearing_now(created.json()["created_at"], field="POST created_at")

    listed = client.get("/api/artifacts/", params={"limit": 100})
    assert listed.status_code == 200, listed.text
    rows = [row for row in listed.json()["items"] if row["document_id"] == doc.id]
    assert rows, "artifact did not come back from the listing endpoint"
    _assert_offset_bearing_now(rows[0]["created_at"], field="GET created_at")


def test_artifact_persisted_naive_is_served_as_utc(client, db) -> None:
    """A row written before the sweep still serializes with an offset.

    The stored wall clock is unchanged — no migration — so the reader's contract
    ("a naive stored value IS UTC") is what makes the offset appear.
    """
    doc = Document(name="legacy-naive-row.txt")
    db.save(doc)
    stored = datetime(2026, 6, 11, 12, 0, 0, 123456)
    db.save(
        Artifact(
            document_id=doc.id,
            artifact_type="transcription",
            content="legacy",
            created_at=stored,
        )
    )

    listed = client.get("/api/artifacts/", params={"limit": 100})
    assert listed.status_code == 200, listed.text
    rows = [row for row in listed.json()["items"] if row["document_id"] == doc.id]
    assert rows, "legacy artifact did not come back from the listing endpoint"

    text = rows[0]["created_at"]
    assert text.endswith("+00:00"), text
    parsed = datetime.fromisoformat(text)
    # Same wall clock, now self-describing: interpreted, never shifted.
    assert parsed == stored.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Activity + workflow runs (the activity monitor surface from the report)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logged_activity_round_trips_through_duckdb_with_an_offset(
    tmp_path,
) -> None:
    tracker = ActivityTracker(str(tmp_path / "activity.duckdb"))
    logged = tracker.log(ActivityType.WORKFLOW_STARTED, "round trip")
    assert logged.timestamp.tzinfo is not None
    await tracker.wait_for_pending_saves()

    from fichero_server.workflows.activity_types import ActivityFilter

    queried = await tracker.store.query(ActivityFilter(limit=10))
    assert queried, "activity did not persist"
    _assert_offset_bearing_now(
        queried[0].timestamp.isoformat(), field="activity timestamp"
    )
    # to_dict() is what the SSE stream and the REST response are built from.
    _assert_offset_bearing_now(
        queried[0].to_dict()["timestamp"], field="activity to_dict timestamp"
    )


@pytest.mark.asyncio
async def test_workflow_run_round_trips_through_duckdb_with_an_offset(
    tmp_path,
) -> None:
    tracker = ActivityTracker(str(tmp_path / "activity.duckdb"))
    await tracker.store.save_workflow_run(
        thread_id="thread-4347",
        workflow_id="wf-4347",
        workflow_name="Timestamp Round Trip",
        started_at=utc_now(),
    )

    run = await tracker.store.get_workflow_run("thread-4347")
    assert run is not None
    _assert_offset_bearing_now(run.started_at.isoformat(), field="run started_at")


@pytest.mark.asyncio
async def test_workflow_run_written_naive_is_read_as_utc(tmp_path) -> None:
    """Pre-sweep runs keep their wall clock and gain the offset on read."""
    tracker = ActivityTracker(str(tmp_path / "activity.duckdb"))
    stored = datetime(2026, 6, 11, 12, 0, 0)
    await tracker.store.save_workflow_run(
        thread_id="thread-legacy",
        workflow_id="wf-legacy",
        workflow_name="Legacy Run",
        started_at=stored,
    )

    run = await tracker.store.get_workflow_run("thread-legacy")
    assert run is not None
    assert run.started_at == stored.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# The storage layer itself: an aware UTC write must not be shifted on the way in
# ---------------------------------------------------------------------------


def test_aware_utc_write_is_not_shifted_by_the_duckdb_session_timezone(db) -> None:
    """The regression that made a naive sweep useless.

    DuckDB shifts an aware datetime into the *session* timezone before dropping
    the offset for a naive ``TIMESTAMP`` column. Unless connections are pinned to
    UTC, an aware ``12:00Z`` lands on disk as ``09:00`` on a UTC-3 machine —
    exactly the value the old naive code wrote.
    """
    doc = Document(name="session-timezone.txt")
    db.save(doc)
    written = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)
    artifact = Artifact(
        document_id=doc.id,
        artifact_type="transcription",
        created_at=written,
    )
    db.save(artifact)

    reloaded = db.get(Artifact, artifact.id)
    assert reloaded is not None
    assert reloaded.created_at == written

    # And the raw column holds the UTC wall clock, not the local one.
    row = db._execute(
        'SELECT created_at FROM "artifacts" WHERE id = $id',
        {"id": artifact.id},
        fetch="one",
    )
    assert row is not None
    raw = row[0]
    assert raw.replace(tzinfo=None) == written.replace(tzinfo=None)


def test_model_defaults_are_timezone_aware() -> None:
    """The default_factory clock is the aware one, on every persisted model."""
    assert Artifact(document_id="d", artifact_type="t").created_at.tzinfo is not None
    assert Document(name="t.txt").created_at.tzinfo is not None
