"""The startup warm-ups are quiet where there is nothing to warm, and a refusal is one line (416 LOW).

WHY: the Vision locale warm-up warned on every non-macOS start, and `_jobs_say` logged a traceback for an expected
refusal (the job table cannot be read), flooding the log.
"""
from __future__ import annotations

import logging

from fichero_server.importers import derivatives
from fichero_server.workflows.tools import vision_base


def test_the_locale_warm_up_is_silent_off_macos(monkeypatch, caplog):
    def explode():
        raise AssertionError("must not ask Vision off macOS")

    monkeypatch.setattr(vision_base.sys, "platform", "linux")
    monkeypatch.setattr(vision_base, "_supported_vision_locales", explode)
    with caplog.at_level(logging.DEBUG):
        vision_base.warm_supported_locales()
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_an_unreadable_job_table_is_one_line_not_a_traceback(monkeypatch, caplog):
    from fichero_server.db import manager
    from fichero_server.execution import jobs

    class Db:
        pass

    monkeypatch.setattr(manager.db_manager, "open_database", lambda key: Db())
    monkeypatch.setattr(jobs, "queue_state", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("locked")))
    monkeypatch.setattr(derivatives, "jobs_say_failure", None)
    with caplog.at_level(logging.WARNING):
        assert derivatives._jobs_say("/tmp/lib") is None
    records = [r for r in caplog.records if "job table unreadable" in r.getMessage()]
    assert len(records) == 1 and records[0].exc_info is None
