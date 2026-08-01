"""#4381: the dev engine's reloader is OPT-IN, never inferred.

The engine used to default reload ON whenever it detected a Briefcase dev
bundle — and its --reload-dir was the same tree the manager merges lane
branches into, so every merge restarted the engine mid-session (dropped SSE,
sign-in failures) and masked #4379's real defect. The launch profile must ASK
for reload; nothing about where the code happens to be checked out may imply
it.
"""

from __future__ import annotations

import fichero_server.__main__ as backend_main


def test_reload_defaults_off_regardless_of_checkout(monkeypatch):
    monkeypatch.delenv("FICHERO_BACKEND_RELOAD", raising=False)
    monkeypatch.delenv("FICHERO_BACKEND_STABLE_MODE", raising=False)
    # The old defect: a dev-bundle checkout IMPLIED reload (via a
    # _is_briefcase_dev_bundle() default, now deleted along with the
    # inference). With no env set, nothing about the checkout may turn it on.
    assert backend_main._reload_enabled() is False
    assert not hasattr(backend_main, "_is_briefcase_dev_bundle"), (
        "the dev-bundle inference came back — reload must stay opt-in (#4381)"
    )


def test_reload_is_granted_when_explicitly_requested(monkeypatch):
    monkeypatch.setenv("FICHERO_BACKEND_RELOAD", "1")
    monkeypatch.delenv("FICHERO_BACKEND_STABLE_MODE", raising=False)

    assert backend_main._reload_enabled() is True


def test_stable_mode_overrides_an_explicit_request(monkeypatch):
    monkeypatch.setenv("FICHERO_BACKEND_RELOAD", "1")
    monkeypatch.setenv("FICHERO_BACKEND_STABLE_MODE", "1")

    assert backend_main._reload_enabled() is False


# ---------------------------------------------------------------------------
# #4400 — an unsupervised engine says so; it never silently opts out
# ---------------------------------------------------------------------------


def test_watchdog_without_a_parent_pid_warns_loudly(monkeypatch, caplog):
    """No FICHERO_PARENT_PID used to mean a silent return — an immortal
    engine nobody knew was unsupervised. It must SAY it (#4400)."""
    import asyncio
    import logging

    from fichero_server.api import main as api_main

    monkeypatch.delenv("FICHERO_PARENT_PID", raising=False)
    with caplog.at_level(logging.WARNING, logger=api_main.__name__):
        asyncio.run(api_main._watch_parent_process())

    assert any("UNSUPERVISED ENGINE" in r.message for r in caplog.records), (
        "the watchdog opted out silently — the #4400 immortal-engine shape"
    )


def test_watchdog_with_a_garbage_parent_pid_warns_loudly(monkeypatch, caplog):
    import asyncio
    import logging

    from fichero_server.api import main as api_main

    monkeypatch.setenv("FICHERO_PARENT_PID", "not-a-pid")
    with caplog.at_level(logging.WARNING, logger=api_main.__name__):
        asyncio.run(api_main._watch_parent_process())

    assert any("UNSUPERVISED ENGINE" in r.message for r in caplog.records)


def test_launch_script_supplies_an_owner_pid():
    """start_backend.sh must hand the engine an owner ($PPID) so a
    script-launched engine dies with its terminal instead of becoming
    immortal (#4400). Source-level: the script is bash, but the contract
    is one line and this fails the moment it is dropped."""
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "start_backend.sh"
    ).read_text()
    assert 'FICHERO_PARENT_PID="${FICHERO_PARENT_PID:-$PPID}"' in script
