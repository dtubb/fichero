"""Keychain reads have THREE outcomes, and the third must never wear the
second's clothes (#4534).

The bug this pins: `get_api_key` returned `None` for every failure that was not
rc 44, after a `logger.debug` that is invisible at the default level. So "the
item exists and this process is not allowed to read it" was reported to the
whole app as "there is no key".

That is not hypothetical. Daniel's OpenRouter key was written 2026-07-27 and is
still in his login keychain; after a reboot the item's ACL no longer trusted the
CLI-launched engine, `security` exited 36 rather than prompting (it has no UI
session), and `/api/providers/openrouter/api-key/status` answered
`has_api_key: false, keychain_available: true`. Both fields were individually
defensible and the sentence they formed was false.

Every test here FAILS against the old implementation, which is the point:
rc 36 used to be indistinguishable from rc 44.
"""

from __future__ import annotations

import logging

import pytest

from fichero_server.security import keychain
from fichero_server.security.keychain import (
    ProviderKeyState,
    KeychainUnreadableError,
)


@pytest.fixture
def security_result(monkeypatch):
    """Drive `security`'s exit code and output without touching a real keychain."""

    def _install(returncode: int, stdout: str = "", stderr: str = ""):
        monkeypatch.setattr(keychain, "_is_macos", lambda: True)
        monkeypatch.setattr(
            keychain,
            "_run_security",
            lambda *args, **kwargs: (returncode, stdout, stderr),
        )

    return _install


# ---------------------------------------------------------------------------
# The three states
# ---------------------------------------------------------------------------


def test_readable_key_is_found(security_result):
    security_result(0, stdout="sk-or-v1-realkey\n")

    result = keychain.lookup_api_key("openrouter")

    assert result.state is ProviderKeyState.FOUND
    assert result.key == "sk-or-v1-realkey"
    assert keychain.get_api_key("openrouter") == "sk-or-v1-realkey"
    assert keychain.has_api_key("openrouter") is True


def test_rc44_is_genuinely_absent(security_result):
    """errSecItemNotFound is the ONE code that means "not there"."""
    security_result(44, stderr="The specified item could not be found in the keychain.")

    result = keychain.lookup_api_key("openrouter")

    assert result.state is ProviderKeyState.ABSENT
    assert result.key is None
    # Absent is not an error: this must NOT raise.
    assert keychain.get_api_key("openrouter") is None


def test_rc36_is_unreadable_not_absent(security_result):
    """THE regression test. Old code returned None here, same as rc 44."""
    security_result(36, stderr="")

    result = keychain.lookup_api_key("openrouter")

    assert result.state is ProviderKeyState.UNREADABLE
    assert result.state is not ProviderKeyState.ABSENT
    assert result.detail  # it must say something


@pytest.mark.parametrize("returncode", [1, 25, 36, 51, -1, 128])
def test_every_non_44_failure_is_unreadable(security_result, returncode):
    """The rule is general, not a special case for 36. A locked keychain, a
    timeout, and an ACL refusal are all "we could not read it"."""
    security_result(returncode, stderr="boom")

    assert keychain.lookup_api_key("x").state is ProviderKeyState.UNREADABLE


def test_success_with_empty_output_is_not_treated_as_absent(security_result):
    """rc 0 and nothing on stdout: the tool claims success and gave us no key.
    That is not an absence we can vouch for, so it must not be reported as one."""
    security_result(0, stdout="")

    result = keychain.lookup_api_key("openrouter")

    assert result.state is ProviderKeyState.UNREADABLE


# ---------------------------------------------------------------------------
# The contract callers rely on
# ---------------------------------------------------------------------------


def test_get_api_key_raises_rather_than_returning_the_absent_answer(security_result):
    security_result(36, stderr="denied")

    with pytest.raises(KeychainUnreadableError) as excinfo:
        keychain.get_api_key("openrouter")

    # The error must carry WHAT and WHY, not just fail.
    assert "openrouter" in str(excinfo.value)
    assert excinfo.value.detail == "denied"


def test_unreadable_is_logged_at_warning_not_debug(security_result, caplog):
    """`logger.debug` for a credential read failure is the same as not logging,
    which is how this survived to a user report."""
    security_result(36, stderr="denied")

    with caplog.at_level(logging.WARNING, logger=keychain.__name__):
        keychain.lookup_api_key("openrouter")

    assert any(r.levelno >= logging.WARNING for r in caplog.records), (
        "an unreadable credential must be logged at warning or above"
    )


def test_api_key_state_never_carries_the_secret(security_result):
    """A status caller has no business holding the key -- so the result it gets
    can be logged or serialized without leaking it."""
    security_result(0, stdout="sk-or-v1-realkey")

    state = keychain.api_key_state("openrouter")

    assert state.state is ProviderKeyState.FOUND
    assert state.key is None


def test_has_api_key_is_false_for_unreadable_but_state_still_distinguishes(
    security_result,
):
    """`has_api_key` stays a bool because most callers want one. The point is
    that the truth is still reachable next to it -- flattening is a caller's
    choice now, not the only option."""
    security_result(36)

    assert keychain.has_api_key("openrouter") is False
    assert keychain.api_key_state("openrouter").state is ProviderKeyState.UNREADABLE


def test_non_macos_is_absent_with_a_reason(monkeypatch):
    """Off macOS there genuinely is no key IN A KEYCHAIN -- an honest absence,
    and it says why rather than being a bare None."""
    monkeypatch.setattr(keychain, "_is_macos", lambda: False)

    result = keychain.lookup_api_key("openrouter")

    assert result.state is ProviderKeyState.ABSENT
    assert result.detail == "keychain is macOS-only"


# ---------------------------------------------------------------------------
# Sibling: the same defect shape in the provider list
# ---------------------------------------------------------------------------


def test_failed_dump_logs_that_the_list_is_unknown(monkeypatch, caplog):
    """An empty list means "no provider has a key". A failed dump is not that,
    and a locked keychain would have reported every provider as unconfigured."""
    monkeypatch.setattr(keychain, "_is_macos", lambda: True)
    monkeypatch.setattr(keychain, "_run_security", lambda *a, **k: (36, "", "denied"))

    with caplog.at_level(logging.WARNING, logger=keychain.__name__):
        providers = keychain.list_providers()

    assert providers == []
    assert any("UNKNOWN" in r.getMessage() for r in caplog.records), (
        "a failed dump must not pass silently as an empty provider list"
    )
