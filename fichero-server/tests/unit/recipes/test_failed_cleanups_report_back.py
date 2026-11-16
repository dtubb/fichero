"""Best-effort cleanups hand a failure back to the caller as well as logging it (#6354, the swallowed-exception seam)."""

from __future__ import annotations

from types import SimpleNamespace

from fichero_server.recipes import runner


def test_a_run_cap_that_cannot_be_cleared_says_so_and_a_cleared_one_says_so(monkeypatch):
    monkeypatch.setattr(runner, "_library", lambda db: "/tmp/p.fichero")
    monkeypatch.setattr(runner.spend, "clear_run_cap", lambda library, job_id: None)
    assert runner._drop_the_run_cap(object(), "job-1") is True

    def broken(library, job_id):
        raise OSError("read-only")

    monkeypatch.setattr(runner.spend, "clear_run_cap", broken)
    assert runner._drop_the_run_cap(object(), "job-1") is False


def test_a_link_library_the_registry_cannot_take_says_so(monkeypatch):
    from fichero_server.api.routes.auth import pairing
    from fichero_server.api.routes.library import registry

    saved = []
    ok = SimpleNamespace(query=lambda model, path: [], save=saved.append)
    monkeypatch.setattr(registry, "get_global_database", lambda: ok)
    assert pairing._register_link_library("/tmp/p.fichero") is True
    assert len(saved) == 1

    def broken():
        raise RuntimeError("registry locked")

    monkeypatch.setattr(registry, "get_global_database", broken)
    assert pairing._register_link_library("/tmp/p.fichero") is False
