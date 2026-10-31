"""A number saved as text (a node's `max_tokens` or `timeout` typed into a field) is read as the number, or
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


@pytest.mark.parametrize("bad", ["lots", "", "8192.7", 4096.5, "inf", float("inf"), float("nan"), True, "-5", -5, -5.0])
def test_a_ceiling_that_is_not_a_whole_number_above_zero_is_said_in_words(bad):
    with pytest.raises(ValueError, match="max_tokens"):
        LLMConfig(provider="anthropic", model="m", max_tokens=bad)


@pytest.mark.parametrize("bad", ["0.5", 0.5, 2.7, "inf", "-1", -1])
def test_a_timeout_that_is_not_a_whole_number_above_zero_is_said_in_words(bad):
    with pytest.raises(ValueError, match="timeout"):
        LLMConfig(provider="anthropic", model="m", timeout=bad)


def test_a_whole_number_written_as_a_float_is_that_number():
    assert LLMConfig(provider="anthropic", model="m", max_tokens="8192.0", timeout=30.0).max_tokens == 8192


@pytest.mark.parametrize("zero", [0, 0.0, "0"])
def test_zero_is_no_ceiling_however_it_is_written(zero):
    assert LLMConfig(provider="anthropic", model="m", max_tokens=zero).max_tokens == 0
