"""A number saved as text (a node's `max_tokens` typed into a field, a stored `preset_version`) is read as the number, or
refused in words naming the field, never a `'>' not supported between 'str' and 'int'` hours into a run (#6298)."""
from __future__ import annotations

import dataclasses

import pytest

from fichero_server.llm import LLMConfig


def test_a_ceiling_saved_as_text_is_the_number():
    config = LLMConfig(provider="anthropic", model="m", max_tokens="8192", timeout="90")
    assert config.max_tokens == 8192 and config.timeout == 90
    # the two places a run compares or doubles it: the request guard and the empty-answer retry
    assert config.max_tokens > 0
    assert max(8192, dataclasses.replace(config, max_tokens="4096").max_tokens * 2) == 8192


def test_a_ceiling_that_is_not_a_number_is_said_in_words():
    with pytest.raises(ValueError, match="max_tokens"):
        LLMConfig(provider="anthropic", model="m", max_tokens="lots")


def test_a_stored_preset_version_as_text_does_not_break_the_upgrade_check():
    from fichero_server.workflows.default_workflows import _version

    assert _version("2") == 2 and _version(3) == 3 and _version(None) == 1 and _version("x") == 1
