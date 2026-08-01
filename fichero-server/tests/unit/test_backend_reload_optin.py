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
