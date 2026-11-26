import pytest

from fichero_server.execution import jobs


@pytest.fixture(autouse=True)
def fresh_scheduler(monkeypatch, app_db):
    """A scheduler with nothing loaded and the pause off, per test: the module's scheduler and
    the pause are process-wide, and a model left loaded by another test would change the order."""
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_mode("automatic")  # neither paused nor started (`activity.mode.start-stop`)
    yield
    jobs.set_mode("automatic")
