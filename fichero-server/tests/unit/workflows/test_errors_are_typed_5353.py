"""A runtime failure reaches the job as its typed kind, from the exception the runtime raised, not from
words in its message (#5353, `runtime.errors-are-typed`)."""
from __future__ import annotations

import pytest

from fichero_server.execution.runner import _classify_provider_error
from fichero_server.execution.throttle import MemoryShortError
from fichero_server.llm import AppleUnavailableError, LocalOnlyViolationError, ProviderQuotaError
from fichero_server.llm.local_inference import LocalModelMemoryUnavailableError, LocalModelNotInstalledError


@pytest.mark.parametrize("exc, category", [
    (ProviderQuotaError("openai"), "quota"),
    (LocalOnlyViolationError("openai"), "egress_refused"),
    (MemoryShortError("short"), "memory"),
    (LocalModelMemoryUnavailableError("too big"), "memory"),
    (LocalModelNotInstalledError("nope"), "model_missing"),
    (AppleUnavailableError("off"), "unavailable_in_this_build"),
])
def test_the_exception_type_decides_the_category_whatever_its_words(exc, category):
    # Words that the old text matching would have read as something else ("timeout" -> network).
    assert _classify_provider_error("connection timeout while waiting", exc)["category"] == category


def test_an_exception_with_no_type_of_its_own_still_reads_its_words():
    assert _classify_provider_error("HTTP 429 rate limit", RuntimeError("HTTP 429 rate limit"))["category"] == "quota"
