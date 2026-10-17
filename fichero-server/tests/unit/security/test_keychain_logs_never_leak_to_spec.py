"""keys.key-never-in-logs, keychain half (#4821).

Spec (docs/contributor_manual/specs/ai/ai-settings.md, keys.key-never-in-logs):
keychain.py's set_api_key / delete_api_key log lines name the provider and
never the key value. Nothing guarded that until now, so a future debug line
that formats the key would ship green. A sentinel key is pushed through every
success and failure path and must not appear in any log record.
"""

from __future__ import annotations

import logging

import pytest

from fichero_server.security import keychain

SENTINEL = "sk-SENTINEL-4821-do-not-log"


@pytest.fixture
def security_result(monkeypatch):
    """Run the real set/delete code, with only the OS boundary faked.

    Yields a one-element list: the (returncode, stdout, stderr) the fake
    `security` call returns. Tests overwrite element 0 to pick a path."""
    monkeypatch.setattr(keychain, "_is_macos", lambda: True)
    monkeypatch.setattr(keychain, "_invalidate_llm_api_key_cache", lambda provider: None)
    result = [(0, "", "")]
    monkeypatch.setattr(keychain, "_run_security", lambda *args: result[0])
    return result


def _assert_no_key_in_logs(caplog):
    assert caplog.records, "expected at least one log line to inspect"
    for record in caplog.records:
        assert SENTINEL not in record.getMessage()
        assert SENTINEL not in str(record.args)


@pytest.mark.usefixtures("security_result")
def test_set_success_never_logs_the_key(caplog):
    caplog.set_level(logging.DEBUG, logger=keychain.logger.name)

    assert keychain.set_api_key("openrouter", SENTINEL) is True

    _assert_no_key_in_logs(caplog)


def test_set_failure_never_logs_the_key(security_result, caplog):
    caplog.set_level(logging.DEBUG, logger=keychain.logger.name)
    security_result[0] = (1, "", "security: user interaction is not allowed")

    assert keychain.set_api_key("openrouter", SENTINEL) is False

    _assert_no_key_in_logs(caplog)
    assert any("Failed to store API key" in r.getMessage() for r in caplog.records)


@pytest.mark.usefixtures("security_result")
def test_delete_success_never_logs_the_key(caplog):
    caplog.set_level(logging.DEBUG, logger=keychain.logger.name)

    assert keychain.delete_api_key("openrouter") is True

    for record in caplog.records:
        assert SENTINEL not in record.getMessage()


def test_delete_failure_never_logs_the_key(security_result, caplog):
    caplog.set_level(logging.DEBUG, logger=keychain.logger.name)
    security_result[0] = (1, "", "security: boom")

    assert keychain.delete_api_key("openrouter") is False

    for record in caplog.records:
        assert SENTINEL not in record.getMessage()
