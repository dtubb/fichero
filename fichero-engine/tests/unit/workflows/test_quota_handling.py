"""
Unit tests for two fixes in commit 4a6622fc (#1222):

  Fix 1: _is_quota_error() in fichero.workflows.builder
    — detects non-retriable quota/rate-limit errors so the workflow can
      pause immediately instead of burning retries.

  Fix 2: Defensive to_dict() in fichero.workflows.activity_types.Activity
    — handles cases where type/level are stored as plain strings (not Enum
      instances) without raising AttributeError.
"""

from __future__ import annotations

import uuid
from datetime import datetime


from fichero.workflows.builder import _is_quota_error
from fichero.workflows.activity_types import Activity, ActivityType, ActivityLevel


# ---------------------------------------------------------------------------
# Fix 1: _is_quota_error
# ---------------------------------------------------------------------------

class TestIsQuotaError:
    """_is_quota_error correctly identifies non-retriable provider errors."""

    def test_http_403_returns_true(self):
        """An exception whose string representation contains '403' is a quota error."""
        exc = Exception("HTTP 403 Forbidden: access denied")
        assert _is_quota_error(exc) is True

    def test_quota_exceeded_returns_true(self):
        """Exception message containing 'quota exceeded' is detected."""
        exc = Exception("ResourceExhausted: quota exceeded for this project")
        assert _is_quota_error(exc) is True

    def test_rate_limit_with_space_returns_true(self):
        """Exception message containing 'rate limit' (with space) is detected."""
        exc = Exception("Too many requests: rate limit reached, retry after 60s")
        assert _is_quota_error(exc) is True

    def test_rate_limit_with_underscore_returns_true(self):
        """Exception message containing 'rate_limit' (with underscore) is detected."""
        exc = Exception("RateLimitError: rate_limit exceeded")
        assert _is_quota_error(exc) is True

    def test_key_limit_returns_true(self):
        """Exception message containing 'key limit' is detected."""
        exc = Exception("API key limit reached for your plan")
        assert _is_quota_error(exc) is True

    def test_generic_500_returns_false(self):
        """A generic server error should not be treated as a quota error."""
        exc = Exception("HTTP 500 Internal Server Error: upstream timeout")
        assert _is_quota_error(exc) is False

    def test_empty_message_returns_false(self):
        """An exception with an empty message is not a quota error."""
        exc = Exception("")
        assert _is_quota_error(exc) is False

    def test_none_equivalent_message_returns_false(self):
        """An exception constructed with no args produces 'None' or empty str — not quota."""
        # Exception() produces empty str; Exception(None) produces 'None' str.
        # Neither should match quota indicators.
        exc_no_args = Exception()
        assert _is_quota_error(exc_no_args) is False

    def test_case_insensitive_detection(self):
        """Detection is case-insensitive (indicators are lowercased)."""
        exc = Exception("QUOTA EXCEEDED for this billing period")
        assert _is_quota_error(exc) is True

    def test_generic_connection_error_returns_false(self):
        """A connection-reset error with no quota indicators returns False."""
        exc = ConnectionError("Connection reset by peer")
        assert _is_quota_error(exc) is False

    def test_value_error_with_403_in_body_returns_true(self):
        """Any exception subclass works — detection is string-based."""
        exc = ValueError("Received 403 from provider endpoint")
        assert _is_quota_error(exc) is True


# ---------------------------------------------------------------------------
# Fix 2: Activity.to_dict() defensive enum handling
# ---------------------------------------------------------------------------

def _make_activity(**overrides) -> Activity:
    """Create a minimal Activity, allowing field overrides for testing."""
    defaults = dict(
        id=str(uuid.uuid4()),
        type=ActivityType.WORKFLOW_STARTED,
        level=ActivityLevel.INFO,
        timestamp=datetime(2026, 5, 25, 12, 0, 0),
        message="test message",
    )
    defaults.update(overrides)
    return Activity(**defaults)


class TestActivityToDictEnumSafety:
    """Activity.to_dict() must not raise when type or level are plain strings."""

    def test_proper_enum_types_serialise_correctly(self):
        """Baseline: enum instances are serialised to their string values."""
        act = _make_activity(
            type=ActivityType.WORKFLOW_COMPLETED,
            level=ActivityLevel.INFO,
        )
        result = act.to_dict()

        assert result["type"] == "workflow_completed"
        assert result["level"] == "info"
        assert result["message"] == "test message"
        assert result["id"] == act.id

    def test_string_type_field_does_not_raise(self):
        """If type is already a string (not Enum), to_dict() must not AttributeError."""
        act = _make_activity()
        # Directly overwrite the field to simulate a string coming from the DB
        object.__setattr__(act, "type", "workflow_started")

        # Must not raise
        result = act.to_dict()
        assert result["type"] == "workflow_started"

    def test_string_level_field_does_not_raise(self):
        """If level is already a string (not Enum), to_dict() must not AttributeError."""
        act = _make_activity()
        object.__setattr__(act, "level", "warning")

        result = act.to_dict()
        assert result["level"] == "warning"

    def test_both_fields_as_strings_does_not_raise(self):
        """If both type and level are strings, to_dict() must not AttributeError."""
        act = _make_activity()
        object.__setattr__(act, "type", "node_started")
        object.__setattr__(act, "level", "error")

        result = act.to_dict()
        assert result["type"] == "node_started"
        assert result["level"] == "error"

    def test_enum_type_value_matches_string_type_value(self):
        """Serialised output is identical whether type is Enum or its string value."""
        act_enum = _make_activity(type=ActivityType.NODE_COMPLETED, level=ActivityLevel.INFO)
        act_str = _make_activity(type=ActivityType.NODE_COMPLETED, level=ActivityLevel.INFO)
        object.__setattr__(act_str, "type", "node_completed")

        assert act_enum.to_dict()["type"] == act_str.to_dict()["type"]

    def test_to_dict_includes_all_expected_keys(self):
        """to_dict() always emits all required keys regardless of enum vs string."""
        act = _make_activity(
            workflow_id="wf-test",
            thread_id="thr-1",
            node_id="summarize",
            duration_ms=123.4,
            error=None,
            metadata={"files": 3},
        )
        result = act.to_dict()

        expected_keys = {
            "id", "type", "level", "timestamp", "message",
            "workflow_id", "batch_id", "thread_id", "node_id",
            "metadata", "duration_ms", "error",
        }
        assert expected_keys == set(result.keys())
        assert result["workflow_id"] == "wf-test"
        assert result["duration_ms"] == 123.4
        # metadata values are coerced to strings
        assert result["metadata"]["files"] == "3"
