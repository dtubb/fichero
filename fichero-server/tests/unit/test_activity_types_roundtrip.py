from datetime import datetime, timezone

from fichero_server.workflows.activity_types import Activity, ActivityLevel, ActivityType


def test_activity_round_trip_serializes_metadata_for_api_clients() -> None:
    activity = Activity(
        id="event-1",
        type=ActivityType.NODE_COMPLETED,
        level=ActivityLevel.INFO,
        timestamp=datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc),
        message="done",
        metadata={"attempt": 2, "cached": False, "none": None},
    )

    payload = activity.to_dict()

    assert payload["metadata"] == {"attempt": "2", "cached": "False", "none": None}
    restored = Activity.from_dict(payload)
    assert restored.type is ActivityType.NODE_COMPLETED
    assert restored.timestamp == activity.timestamp
