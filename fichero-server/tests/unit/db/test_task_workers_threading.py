"""Thread-safety tests for the task workers (#2509 / #2508), run on their job host (#5353).

The workers run their database calls on arbitrary ``asyncio.to_thread`` pool
threads, so they must NOT capture the queue's ``self.database`` and ship it
across the thread boundary — they obtain the Database from ``db_manager`` from
WITHIN the pool thread (#2509). Under the single-connection model (#2508) that
call returns the ONE shared Database for the package (one connection serialized
by one lock), so cross-thread access is safe by construction.

These tests use REAL databases (no mocking of the unit under test) so a
regression to capturing a foreign connection surfaces as a real DuckDB
threading error.
"""

import asyncio
import threading
from contextlib import asynccontextmanager

import pytest

from fichero_server.db import db_manager
from fichero_server.models import Document
from fichero_server.workflows.task_types import BackgroundTask, TaskConfig
from fichero_server.workflows.task_workers import _JobTask
from fichero_server.workflows.tasks import TaskStatus, TaskType


class _Queue:
    """Runs workers as their jobs do: each on its own `_JobTask` host, on a REAL package Database."""

    def __init__(self, database):
        self.database = database

    async def create_task(self, task_type, name):
        return BackgroundTask(task_id=f"job-{name}", task_type=task_type, name=name, status=TaskStatus.RUNNING,
                              config=TaskConfig(task_type=task_type))

    async def _run(self, kind, task):
        task.result = await getattr(_JobTask(self.database, task.task_id), f"_do_{kind}")(task)
        task.status = TaskStatus.COMPLETED if task.result.success else TaskStatus.FAILED
        return task.result

    async def _execute_metrics(self, task):
        return await self._run("metrics", task)

    async def _execute_reindex(self, task):
        return await self._run("reindex", task)


@pytest.fixture
def real_task_queue(test_package, tmp_path):
    """A factory for the workers' runner wired to a REAL package Database (entered inside each
    test, as before)."""

    @asynccontextmanager
    async def running():
        database = db_manager.get_database(test_package)
        yield _Queue(database), test_package, database

    return running


@pytest.mark.asyncio
async def test_db_call_resolves_connection_inside_pool_thread(
    real_task_queue, monkeypatch
):
    """The Database driven inside the to_thread callable must be obtained via
    db_manager FROM the pool thread (#2509), not captured+shipped from the
    event-loop thread. Under #2508 it resolves to the one shared package
    Database."""
    async with real_task_queue() as (queue, package, _):
        await _assert_pool_thread_resolution(queue, package, monkeypatch)


async def _assert_pool_thread_resolution(queue, package, monkeypatch):
    package_str = str(package)
    event_loop_ident = threading.get_ident()

    # Seed a couple of real documents (content-less → no embedding needed).
    main_db = db_manager.get_database(package)
    main_db.save(Document(id="doc1", name="Doc 1", page_content=None))
    main_db.save(Document(id="doc2", name="Doc 2", page_content=None))

    # Spy on db_manager.get_database, recording the thread that asks.
    real_get = db_manager.get_database
    calls: list[int] = []

    def spy(path):
        calls.append(threading.get_ident())
        return real_get(path)

    monkeypatch.setattr(db_manager, "get_database", spy)

    task = await queue.create_task(TaskType.METRICS, "Metrics")
    await queue._execute_metrics(task)

    assert task.status == TaskStatus.COMPLETED
    assert calls, "db_manager.get_database was never called inside the worker"

    # Every resolution happened on a POOL thread, never the event-loop thread —
    # i.e. the worker calls get_database from inside the to_thread callable
    # rather than capturing+shipping the queue's Database (#2509).
    assert event_loop_ident not in calls, (
        "Database was resolved on the event-loop thread — the worker is "
        "capturing+shipping a connection across the thread boundary (#2509)"
    )

    # Under the single-connection model (#2508) the manager holds exactly ONE
    # shared Database for the package (keyed by package path, not per-thread);
    # the in-thread get_database calls all return that shared instance.
    assert package_str in db_manager._databases, (
        "no shared Database keyed for the package"
    )
    assert db_manager.get_database(package) is db_manager._databases[package_str]


@pytest.mark.asyncio
async def test_workers_under_concurrent_write_never_raise_threading_error(
    real_task_queue,
):
    """Reindex + metrics running on pool threads concurrently with a
    separate writer thread (on its own keyed connection) must complete
    without raising a DuckDB cross-thread error."""
    async with real_task_queue() as (queue, package, _):
        await _assert_no_threading_error(queue, package)


async def _assert_no_threading_error(queue, package):
    main_db = db_manager.get_database(package)
    for i in range(5):
        main_db.save(Document(id=f"doc{i}", name=f"Doc {i}", page_content=None))

    # A background writer thread hammering the DB on the shared connection —
    # the realistic "API thread writes while worker reindexes" scenario that the
    # single-connection model (#2508) must tolerate (serialized by one lock).
    stop = threading.Event()
    writer_errors: list[Exception] = []

    def writer():
        try:
            wdb = db_manager.get_database(package)
            n = 0
            while not stop.is_set() and n < 50:
                wdb.save(
                    Document(id=f"w{n}", name=f"Writer {n}", page_content=None)
                )
                n += 1
        except Exception as exc:  # pragma: no cover - failure path
            writer_errors.append(exc)

    writer_thread = threading.Thread(target=writer)
    writer_thread.start()
    try:
        tasks = []
        for i in range(4):
            rt = await queue.create_task(TaskType.REINDEX, f"Reindex {i}")
            mt = await queue.create_task(TaskType.METRICS, f"Metrics {i}")
            tasks.append(queue._execute_reindex(rt))
            tasks.append(queue._execute_metrics(mt))
        results = await asyncio.gather(*tasks)
    finally:
        stop.set()
        writer_thread.join(timeout=10)

    assert not writer_errors, f"Writer thread raised: {writer_errors}"
    for result in results:
        assert result.success is True
