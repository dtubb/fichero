"""
DatabaseManager — connection pool for multi-library Fichero packages.

Each .fichero package directory gets its own Database instance.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from fichero_server.api.change_stream import emit_change
from fichero_server.db.library_paths import nfc_path

if TYPE_CHECKING:
    from fichero_server.db import Database

logger = logging.getLogger(__name__)


class LibraryNotFoundError(FileNotFoundError):
    """A request named a ``.fichero`` package that does not exist (#5136).

    Opening a library never creates one: only ``POST /api/library`` (and the
    engine's own global library) pass ``create=True``. The API maps this to
    a 404 whose detail names the missing path.
    """

    def __init__(self, package_path: str | Path):
        self.package_path = str(package_path)
        super().__init__(
            f"Library does not exist: {self.package_path}. "
            "Create it with POST /api/library (New Library) first."
        )


class DatabaseBusy(RuntimeError):
    """A consistent copy of a library's database could not be taken in time: another connection
    held a write transaction open past the wait (#5185). Named, so a caller refuses with the reason
    instead of a 500 -- and nothing was copied."""


class DatabaseManager:
    """Manages Database instances for package documents — ONE per package,
    shared across all threads (#2508).

    Each .fichero package contains its own database files:
    - MyLibrary.fichero/fichero.duckdb
    - MyLibrary.fichero/lance/

    A DuckDB ``Connection`` is not safe for *concurrent* use, but it IS safe
    when serialized by a lock. The manager keeps exactly one ``Database`` (one
    connection, one ``RLock``) per package; ``Database`` already wraps every
    typed read/write in ``with self._lock``, so a single shared instance makes
    that serialization globally effective and read-after-write deterministic
    across threads. Previously the pool was keyed by ``(package, thread_ident)``
    — each thread got its own connection+lock, so the locking never serialized
    across threads and cross-thread correctness rode on DuckDB MVCC alone (the
    root of #2430 per-page loss and #2462 phantom 404s).
    """

    def __init__(self):
        # Key: package_str -> Database. ONE shared connection per package across
        # all threads (#2508); Database._lock then serializes every access
        # globally. NEVER re-introduce a thread_ident in this key — that is the
        # exact hazard #2508 removed (see test_single_connection_guardrail).
        self._databases: dict[str, Database] = {}
        #: One lock PER LIBRARY for its open (#5228). The manager-wide `_lock` was held for a whole
        #: open (~1-6 s), so while one library opened, a request for any OTHER library -- and every
        #: other launch-time open -- waited behind it. Two requests for the same library still get one
        #: open; `_lock` now guards only the dictionaries.
        self._open_locks: dict[str, threading.Lock] = {}
        self._lock = threading.Lock()
        logger.info("DatabaseManager initialized")

    def open_database(self, cache_key: str) -> "Database | None":
        """The package's open Database for a key from `_cache_key`, or None -- a dict read, no lock
        and no path resolution, for a caller that looks its library up on every short statement
        (the workflow NodeCache, #5189). A None means "not open now": call `get_database`."""
        return self._databases.get(cache_key)

    def is_open(self, package_path: str | Path) -> bool:
        """Whether this package already has its shared connection -- without opening it (#5257)."""
        return self._cache_key(Path(nfc_path(package_path))) in self._databases

    def get_database(
        self, package_path: str | Path, *, create: bool = False
    ) -> "Database":
        """Get or open the one shared Database instance for a package.

        The same instance (one DuckDB connection + one RLock) is returned on
        every thread (#2508); all access serializes on that lock.

        Args:
            package_path: Path to the .fichero package directory
                         (e.g., /Users/name/Documents/MyLibrary.fichero)
            create: Create the package (and missing parent folders) when it
                does not exist. Only library creation passes this (#5136):
                every request carries a library header, and opening one used
                to create any path it named -- a health probe with a
                mistyped path made an empty library on disk.

        Raises:
            LibraryNotFoundError: the package directory does not exist and
                ``create`` is False. Nothing is written to disk.

        Returns:
            The single shared Database instance for this package.
        """
        from fichero_server.db import Database
        from fichero_server.db.migrations.schema import (
            migrate_activity_tables,
            migrate_catalogue_chunk_artifact_type,
            migrate_checkpoint_tables,
            migrate_provider_refs_table,
            migrate_saved_search_table,
            migrate_workflow_table,
        )
        from fichero_server.db.paths import is_global_library_package
        from fichero_server.workflows.default_workflows import (
            heal_default_workflow_tree,
            prune_default_workflows,
            seed_default_workflows,
        )

        package_path = Path(nfc_path(package_path))
        package_str = str(package_path)
        cache_key = self._cache_key(package_path)

        with self._lock:
            open_lock = self._open_locks.setdefault(cache_key, threading.Lock())
        with open_lock:
            if cache_key not in self._databases:
                if (
                    not create
                    and not package_path.expanduser().is_dir()
                    and not self._is_engine_global_library(cache_key)
                ):
                    raise LibraryNotFoundError(package_str)
                db_path = package_path / "fichero.duckdb"
                logger.info(
                    f"Creating shared database connection for package: {package_str}"
                )
                import time as _time

                open_started = _time.monotonic()

                db = Database(path=db_path)
                try:
                    # #4983 phase 1: same shared `db.migration_failures` list
                    # `Database.__init__` populated, and the same
                    # `migrate_workflow_table` re-raises on failure (the one
                    # migration that still fails loudly) — an atomic
                    # rollback + ERROR log + recorded failure happen inside
                    # each function now (`_run_atomic_migration`), so this
                    # `except` below only ever fires for that one function,
                    # exactly as before this phase.
                    migrate_workflow_table(db.conn, db.migration_failures)
                    migrate_saved_search_table(db.conn, db.migration_failures)
                    migrate_provider_refs_table(db.conn, db.migration_failures)
                    migrate_activity_tables(db.conn, db.migration_failures)
                    # #4426: collapse unbounded catalogue.chunk.N types.
                    migrate_catalogue_chunk_artifact_type(db.conn, db.migration_failures)
                    migrate_checkpoint_tables(db.conn, db.migration_failures)

                    # Seed default workflow presets (Transcribe, Catalogue) into
                    # the GLOBAL library only (#4102) — they're app-level presets,
                    # and a per-library copy made the same "Default Workflows"
                    # folder appear under every library in the sidebar. A library
                    # keeps its own custom workflows; it just doesn't get the
                    # shipped ones. Seeding is idempotent by workflow name, so a
                    # user who deleted a preset doesn't get it back. Non-global
                    # libraries seeded before this rule are healed by the prune.
                    # Tests set FICHERO_SKIP_DEFAULT_WORKFLOWS=1 so fixtures that
                    # assert on "empty library" keep working without per-test cleanup.
                    import os

                    if os.environ.get("FICHERO_SKIP_DEFAULT_WORKFLOWS") != "1":
                        if is_global_library_package(package_path):
                            seeded = seed_default_workflows(db)
                            if seeded:
                                logger.info(f"Seeded {seeded} default workflow preset(s)")
                            # Libraries seeded before the locked container hold
                            # the preset folders at the tree ROOT — seeding is
                            # name-idempotent so it never fixes them. Re-home
                            # the mirrors + sweep emptied legacy folders (#4102).
                            heal_default_workflow_tree(db)
                        else:
                            prune_default_workflows(db)

                    # NO Inbox seeding here, and none anywhere else (ruling
                    # 2026-08-31): a library opens EMPTY and stays that way
                    # until the user puts something in it. `ensure_inbox_folder`
                    # ran here and re-seeded a deleted Inbox on every open; it
                    # and its module are deleted. The library ROOT is the drop
                    # zone — loose files land there and both root-listing
                    # surfaces show them — so the folder bought nothing.
                    # Existing libraries keep the Inbox they were seeded with,
                    # as ordinary user content.
                except Exception as exc:
                    db.close()
                    logger.exception("Failed to initialize library database: %s", package_str)
                    raise RuntimeError(
                        f"Failed to initialize library database: {package_str}"
                    ) from exc

                with self._lock:
                    self._databases[cache_key] = db
                opened_in = _time.monotonic() - open_started
                # The whole open, named when slow (#5228): the steps inside are timed one by one
                # in Database; this catches the manager's own migrations and seeding too.
                if opened_in > 2.0:
                    logger.warning(
                        "slow library open: %.2fs for %s -- see the 'slow library open step' lines (#5228)",
                        opened_in, package_str,
                    )
                logger.info(f"Database connection created: {db_path}")

                # Resume interrupted post-ingest work (user, live 2026-08-19):
                # the derivative/embed queue is in-memory, so quitting mid-
                # import stranded every still-queued document in `pending` —
                # never embedded, invisible to semantic search. Re-queue them
                # on open; the stages are idempotent (thumbnail is ensure-
                # style, embed skips already-embedded rows).
                if os.environ.get("FICHERO_SKIP_DERIVATIVE_RESUME") != "1":
                    try:
                        from fichero_server.importers.derivatives import (
                            queue_derivatives,
                        )
                        from fichero_server.models import Document, Status

                        stranded = db.query(Document, status=Status.pending)
                        if stranded:
                            logger.info(
                                "Resuming derivatives for %d pending document(s)",
                                len(stranded),
                            )
                            queue_derivatives(stranded, library_path=package_path, db=db, arrived=False)
                    except Exception:
                        logger.exception("Pending-derivative resume failed")

                # Jobs left running at quit or crash go back to waiting and carry on (#5357).
                try:
                    from fichero_server.execution import jobs

                    jobs.resume(db)
                    # A synced folder may have changed while the engine was off (#4952).
                    from fichero_server import sync_folder

                    sync_folder.rescan(db)
                except Exception:
                    logger.exception("Could not resume the library's jobs")

                # Convert the library's stored geometry to the page model, in the background,
                # after the migrations above (#5222, ruled 2026-09-20). Returns at once; it
                # never delays the open, and unconverted pages read through as before.
                try:
                    from fichero_server.maintenance import conversion_on_open

                    conversion_on_open.start(db, cache_key)
                except Exception:
                    logger.exception("Could not start the project conversion")

                emit_change(
                    package_str,
                    type="library.opened",
                    actor="system",
                    metadata={
                        "library_name": package_path.name,
                        "source": "db_manager",
                    },
                )

            return self._databases[cache_key]

    def _is_engine_global_library(self, cache_key: str) -> bool:
        """The engine's OWN global library (the registry and shipped presets) is the one
        package opening may create: it is the engine's state, not a library a request named,
        and a fresh install has none until first use. Matched by the exact configured path,
        never by name, so a header naming some other `global.fichero` is still refused."""
        from fichero_server.db.storage import settings

        return cache_key == self._cache_key(settings.global_library_path)

    @staticmethod
    def _cache_key(package_path: str | Path) -> str:
        """The ONE `_databases` key form for a package: NFC + realpath, so
        `/var/…` and `/private/var/…` spellings of one package share one
        connection (#2518, proven live 2026-08-25: the create flow opened the
        same temp package under both and held two). get/close/quiesce all
        funnel through this — close previously `.resolve()`d while quiesce
        did not, so a `/var`-spelled quiesce could miss the open handle.
        The Database keeps the caller's spelling; only the KEY canonicalizes.
        """
        return os.path.realpath(str(Path(nfc_path(package_path)).expanduser()))

    def close_database(self, package_path: str | Path):
        """Close the shared connection for a package."""
        package_str = self._cache_key(package_path)
        _stop_conversion(package_str)

        with self._lock:
            keys = [k for k in self._databases if k == package_str]
            for key in keys:
                self._databases.pop(key).close()
                logger.info(f"Closed database connection: {package_str}")

    def quiesce_database(
        self,
        package_path: str | Path,
        *,
        checkpoint: bool = True,
        close: bool = False,
        timeout: float | None = 120.0,
    ) -> None:
        """Checkpoint and optionally close a package DB.

        This is the safety seam for filesystem-level snapshot/restore work. All
        writes serialize on the package's single shared connection lock (#2508),
        so taking that lock to CHECKPOINT is sufficient to quiesce managed
        writes; independent direct DuckDB connections outside the manager remain
        outside this lock's scope.
        """
        package_str = self._cache_key(package_path)
        if close:
            _stop_conversion(package_str)

        with self._lock:
            keys = [k for k in self._databases if k == package_str]

            if checkpoint:
                for key in keys:
                    db = self._databases[key]
                    with db._lock:
                        db.conn.execute("CHECKPOINT")
                    logger.info("Checkpointed database: %s", package_str)

            if close:
                for key in keys:
                    self._databases.pop(key).close()
                    logger.info("Closed database connection: %s", package_str)

    def copy_database_file(
        self,
        package_path: str | Path,
        dest: str | Path,
        *,
        source: str | Path | None = None,
        wait: float = 10.0,
    ) -> Path:
        """A CONSISTENT copy of this library's database file.

        Checkpoint and copy as ONE step, without releasing the lock in between
        (#5070 review). `quiesce_database` cannot be used for this: it takes the
        locks, checkpoints, and RETURNS — so a caller that then copies the file
        has given every other writer a window, and the copy can be torn.

        That was survivable while the copy was a belt-and-braces artefact nobody
        proved. It stops being survivable the moment the copy becomes the thing a
        snapshot exports from and a restore restores: a torn copy either fails to
        open or, worse, opens and restores a state the library was never in. That
        is the one thing the record of "what this operation was about to destroy"
        must not be.

        THE LOCK THAT MATTERS IS THE CONNECTION'S, not the registry's. Writes
        serialize on each `Database._lock` (#2508); `self._lock` only protects the
        manager's own cache. So both are held, the inner ones across the copy.

        A library with no managed connection is copied directly — there is no
        writer to exclude, which is the case for a `Database` built outside the
        manager. Such a caller must checkpoint its own connection first; that is
        what `Database.checkpoint()` is for and what the conversion runner does.
        """
        import contextlib
        import shutil

        package = Path(nfc_path(str(package_path)))
        src = Path(source) if source is not None else package / "fichero.duckdb"
        destination = Path(dest)
        package_str = self._cache_key(package_path)

        import time

        # A WRITE IN FLIGHT ON ANOTHER CONNECTION TO THE SAME DATABASE (#5185): a cursor's open
        # transaction, which `Database._lock` does not cover. DuckDB then refuses CHECKPOINT ("there
        # are other write transactions active"), and that surfaced as a 500 from the snapshot route.
        # FORCE CHECKPOINT is NOT the answer: it aborts those transactions -- the write is lost. So
        # WAIT for them: retry, releasing every lock between tries (a writer that needs one to
        # finish must be able to take it), and copy only once a checkpoint succeeded, still under
        # the locks. Bounded: past `wait` seconds the copy is REFUSED by name (`DatabaseBusy`),
        # never taken half-flushed.
        # The ENGINE'S OWN transactions come first: an audited action on another thread holds its
        # connection's `_transaction_gate` from BEGIN to COMMIT and takes `_lock` only per statement,
        # so holding `_lock` alone let this CHECKPOINT run on the shared connection INSIDE that
        # transaction ("the current transaction has transaction local changes" -- a 500, and a
        # checkpoint issued inside someone else's unit of work). Each gate is waited for, bounded
        # by the same deadline, and held across the checkpoint and the copy.
        deadline = time.monotonic() + wait
        pause = 0.02
        busy: Exception | str = "a managed transaction did not finish"
        while True:
            with self._lock:
                managed = [
                    self._databases[key] for key in list(self._databases) if key == package_str
                ]
            with contextlib.ExitStack() as stack:
                gated = True
                for database in managed:
                    if not database._transaction_gate.acquire(timeout=max(0.0, deadline - time.monotonic())):
                        gated = False
                        break
                    stack.callback(database._transaction_gate.release)
                if gated:
                    with contextlib.ExitStack() as locks:
                        # Every managed connection's write lock, held across BOTH the
                        # checkpoint and the copy. Normally there is exactly one. BOUNDED like the
                        # gate: a statement holding the lock past the deadline (a slow write through
                        # the shared connection -- the NodeCache now writes there, #5189) is a
                        # refusal by name, never a hang.
                        locked = True
                        for database in managed:
                            if not database._lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
                                locked = False
                                busy = "a statement held the connection's lock"
                                break
                            locks.callback(database._lock.release)
                        if locked:
                            try:
                                for database in managed:
                                    database.conn.execute("CHECKPOINT")
                            except Exception as exc:  # noqa: BLE001 -- only the busy case is retried
                                if "other write transactions" not in str(exc):
                                    raise
                                busy = exc
                            else:
                                if managed:
                                    logger.info(
                                        "Checkpointed %d connection(s) and copied %s under one lock",
                                        len(managed), package_str,
                                    )
                                shutil.copy2(src, destination)
                                return destination
            if time.monotonic() >= deadline:
                holders = [held for database in managed if (held := database.open_transaction())]
                if holders:
                    holder = f"; holding it: {'; '.join(holders)}"
                else:
                    # Only on a refusal: not worth a module at every engine start (#3950 budget).
                    from fichero_server.db.busy_evidence import threads_in_a_database_call

                    writing = threads_in_a_database_call()
                    holder = ("; no managed transaction is open; in a database call now: "
                              + ("; ".join(writing) or "no thread"))
                raise DatabaseBusy(
                    f"a write transaction stayed open for more than {wait:g}s, so {package_str} could "
                    f"not be checkpointed for a consistent copy{holder} ({busy})"
                )
            time.sleep(pause)
            pause = min(pause * 2, 0.5)

    def close_current_thread(self) -> None:
        """No-op under the single-connection model (#2508).

        Previously each thread owned its own connection and a workflow worker
        closed it in its ``finally`` to avoid leaking. Now there is ONE shared
        connection per package owned by the manager — a worker thread must NOT
        close it (the event loop and every other thread share it). Connection
        teardown is owned by ``close_database`` / ``close_all`` /
        ``quiesce_database``. Kept as a no-op so existing ``finally`` callers
        (e.g. task_workers) need no change.
        """
        return

    @property
    def active_count(self) -> int:
        """Number of packages with an open shared connection."""
        return len(self._databases)

    def open_library_paths(self) -> list[str]:
        """Return a stable snapshot of package paths with live connections."""
        with self._lock:
            return sorted(self._databases)

    def close_all(self):
        """Close every package's shared connection."""
        _stop_conversion(None)
        with self._lock:
            for cache_key, db in list(self._databases.items()):
                db.close()
                logger.info(f"Closed database: {cache_key}")
            self._databases.clear()
            logger.info("All database connections closed")


def _stop_conversion(package_path: str | None) -> None:
    """Stop a library's background conversion at a page boundary BEFORE its connection closes
    (#5222), outside the manager lock: the runner finishes its page, then sees the stop."""
    from fichero_server.maintenance import conversion_on_open

    conversion_on_open.stop(package_path)


# Global singleton
db_manager = DatabaseManager()
