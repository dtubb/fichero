"""Tests for #2234: explicit remote embeddings gating symmetry.

Before the fix, _enforce_embedding_call_allowed() blocked explicit remote
embedding configs when _paid_remote_fallbacks_enabled() was False — even when
the user deliberately chose a remote provider.  chat() and vision() only check
is_local_only(), not the fallback flag.

After the fix, remote embeddings are allowed whenever:
- The provider is local/builtin (always allowed), OR
- local_only mode is OFF (regardless of the paid-fallback flag)

And blocked only when:
- local_only mode is ON (LocalOnlyViolationError)

Covers:
- Remote embedding allowed when fallbacks disabled but local-only OFF
- Remote embedding blocked when local-only ON (LocalOnlyViolationError)
- Local provider always allowed regardless of both flags
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fichero.llm.embeddings import _enforce_embedding_call_allowed


def test_remote_embedding_allowed_when_fallbacks_disabled() -> None:
    """Explicit remote embedding must pass even if paid fallbacks are disabled."""
    with (
        patch("fichero.llm._is_local_or_builtin_provider", return_value=False),
        patch("fichero.llm.is_local_only", return_value=False),
        # paid fallbacks OFF — should NOT block explicit remote embedding
        patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=False),
    ):
        # Must not raise
        result = _enforce_embedding_call_allowed("openai/text-embedding-3-small")
    assert result is None


def test_remote_embedding_blocked_when_local_only() -> None:
    """When local-only mode is ON, remote embedding must raise LocalOnlyViolationError."""
    from fichero.llm import LocalOnlyViolationError

    with (
        patch("fichero.llm._is_local_or_builtin_provider", return_value=False),
        patch("fichero.llm.is_local_only", return_value=True),
    ):
        with pytest.raises(LocalOnlyViolationError):
            _enforce_embedding_call_allowed("openai/text-embedding-3-small")


def test_local_provider_always_allowed() -> None:
    """Local/builtin providers are never gated regardless of other flags."""
    with (
        patch("fichero.llm._is_local_or_builtin_provider", return_value=True),
        patch("fichero.llm.is_local_only", return_value=True),  # even local-only ON
    ):
        # Must not raise
        result = _enforce_embedding_call_allowed("builtin/local-model")
    assert result is None


def test_remote_embedding_allowed_when_both_flags_enabled() -> None:
    """Sanity: remote embedding allowed when nothing is restricted."""
    with (
        patch("fichero.llm._is_local_or_builtin_provider", return_value=False),
        patch("fichero.llm.is_local_only", return_value=False),
        patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=True),
    ):
        result = _enforce_embedding_call_allowed("openai/text-embedding-3-large")
    assert result is None
