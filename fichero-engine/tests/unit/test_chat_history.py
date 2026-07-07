"""Tests for chat conversation history inclusion (#3238).

Verify that prior turns are included in the LLM prompt, that truncation
drops oldest turns, and that empty history is a no-op.
"""

from fichero.api.routes.chat import _build_history_messages, MAX_HISTORY_TURNS


class TestBuildHistoryMessages:
    """_build_history_messages converts stored turns into LangChain messages."""

    def test_empty_history_returns_empty(self):
        assert _build_history_messages([]) == []

    def test_single_turn_included(self):
        msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        result = _build_history_messages(msgs)
        assert len(result) == 2
        assert result[0].content == "Hello"
        assert result[1].content == "Hi!"

    def test_multiple_turns_included_in_order(self):
        msgs = [
            {"role": "user", "content": "Turn 1"},
            {"role": "assistant", "content": "Reply 1"},
            {"role": "user", "content": "Turn 2"},
            {"role": "assistant", "content": "Reply 2"},
        ]
        result = _build_history_messages(msgs)
        assert len(result) == 4
        assert result[0].content == "Turn 1"
        assert result[1].content == "Reply 1"
        assert result[2].content == "Turn 2"
        assert result[3].content == "Reply 2"

    def test_truncation_drops_oldest_turns(self):
        """When history exceeds max_turns, only the most recent pairs are kept."""
        msgs = []
        for i in range(20):
            msgs.append({"role": "user", "content": f"Q{i}"})
            msgs.append({"role": "assistant", "content": f"A{i}"})
        # max_turns=5 → only the last 5 pairs (10 messages)
        result = _build_history_messages(msgs, max_turns=5)
        assert len(result) == 10
        assert result[0].content == "Q15"
        assert result[1].content == "A15"
        assert result[-2].content == "Q19"
        assert result[-1].content == "A19"

    def test_non_pair_messages_skipped(self):
        """Messages that aren't human+assistant pairs are skipped."""
        msgs = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        result = _build_history_messages(msgs)
        assert len(result) == 2
        assert result[0].content == "Hello"

    def test_default_max_turns_matches_constant(self):
        assert MAX_HISTORY_TURNS == 10

    def test_incomplete_pair_at_end_skipped(self):
        """A trailing user message without a reply is not included."""
        msgs = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},  # no reply yet
        ]
        result = _build_history_messages(msgs)
        assert len(result) == 2
        assert result[0].content == "Q1"
