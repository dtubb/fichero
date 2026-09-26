"""Source-model slice 8b (#4924) — converting a whole project: THE PREFLIGHT.

Spec: `segments-and-geometry.md`, "Converting a whole project: the rules";
`build-notes-readings-cascade-orders.md`, "Slice 8b". Pins covered by this
part: `source.convert.snapshot-first-and-proved`,
`.refused-when-disk-is-short`, and the "anything to do?" half of
`.starts-when-a-project-opens`.

**This module converts nothing.** It answers three questions, in order, and
stops at the first refusal:

1. Is there anything to do?  — one query over markers, no writes at all.
2. Will it fit?             — disk, with room to spare.
3. Is there a way back?     — a pinned snapshot, PROVED readable.

Only when all three pass may pages convert, and that is part 2's job in this
same module. Shipping the preflight first is deliberate: **the dangerous part
cannot run until the safe part has proved the snapshot.**

It lives in `maintenance/` because that package's own rule is this design:
"Each pass separates a pure ``plan_*`` (read-only, reportable) from an
``apply_*`` (the writes), because these run against real archives." Real
archives — the Marshall diaries — go through this path, and the failure that
matters is not a slow conversion but one that half-succeeds and leaves a
library in a state nobody chose.

**Progress is the markers, never a counter.** "What is left" is always
"results with boxes and no marker", asked of the database. A quit, a crash or a
second run cannot make that wrong, so nothing here stores a cursor.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from fichero_server.core.timeutil import utc_now
from fichero_server.models.conversion import (
    ConversionFailure,
    ConversionRun,
    ConversionVerdict,
)

logger = logging.getLogger(__name__)

#: How much more than the estimate the disk must have before anything starts.
#: "With room to spare" from the rules, made a number. 2.0 because the estimate
#: itself is a guess built on the last snapshot's size, and a margin that only
#: just covers a guess is not a margin.
DISK_MARGIN = 2.0

#: What a project's new segment/reading records cost per box, as a deliberate
#: over-estimate. A `Segment` row is a handful of numbers, an anchor and a
#: little JSON; 4 KiB each is comfortably above that, and this number's job is
#: to refuse early rather than to be accurate.
#:
#: ponytail: a constant, not a measurement. Measure it if a real project ever
#: refuses when it would in fact have fitted — the failure mode of being too
#: cautious here is a conversion that waits a day, which is cheap.
BYTES_PER_BOX_ESTIMATE = 4096


class ConversionPreflightFailed(RuntimeError):
    """Raised only when preflight cannot reach a verdict at all.

    Distinct from a REFUSAL, which is a verdict (`refused_disk`,
    `refused_snapshot`) and a normal outcome recorded in the report. This is
    "I could not tell", and it must never be read as "nothing to do" — that
    conflation is how a check comes to pass while seeing nothing.
    """


def conversion_scope(db: Any) -> tuple[int, int]:
    """``(results_to_convert, documents_to_convert)`` — step 1, ONE query.

    An unconverted result is an `Artifact` that has boxes and no conversion
    marker (`geometry_superseded_by_pass_id`). That marker IS the progress
    record, which is why this is a question and not a stored counter: ask it
    again after a crash and the answer is still right.

    Counted in SQL rather than by hydrating artifacts, because this runs at
    EVERY project open and a project of twenty thousand pages must not pay for
    a scan that loads every geometry blob to count them.

    A missing `artifacts` table means a library with no artifacts, which
    genuinely has nothing to convert — the one case where an empty answer is
    the true answer rather than blindness.
    """
    sql = """
        SELECT count(*) AS results, count(DISTINCT document_id) AS documents
        FROM artifacts
        WHERE ocr_geometry IS NOT NULL
          AND geometry_superseded_by_pass_id IS NULL
          AND json_array_length(json_extract(ocr_geometry, '$.boxes')) > 0
    """
    try:
        row = db.conn.execute(sql).fetchone()
    except Exception as exc:
        message = str(exc).lower()
        if "artifacts" in message and ("not exist" in message or "catalog" in message):
            return 0, 0
        raise ConversionPreflightFailed(
            f"could not count what is left to convert: {exc}"
        ) from exc
    if row is None:
        raise ConversionPreflightFailed(
            "counting what is left to convert returned no row at all, which is "
            "not the same as counting zero"
        )
    return int(row[0] or 0), int(row[1] or 0)


def _boxes_to_convert(db: Any) -> int:
    """Total boxes across every unconverted result — the record-count estimate."""
    sql = """
        SELECT coalesce(sum(json_array_length(json_extract(ocr_geometry, '$.boxes'))), 0)
        FROM artifacts
        WHERE ocr_geometry IS NOT NULL
          AND geometry_superseded_by_pass_id IS NULL
    """
    try:
        row = db.conn.execute(sql).fetchone()
    except Exception:
        return 0
    return int((row[0] if row else 0) or 0)


def _last_snapshot_bytes(library_path: Path) -> int | None:
    """The last snapshot's size, which is the best guess at the next one's."""
    try:
        from fichero_server.db.storage_snapshots import list_snapshots

        # `list_snapshots` filters by library_NAME, not path (checked, not
        # assumed). A `.fichero` package's name is its stem.
        snapshots = list_snapshots(library_name=library_path.stem)
    except Exception as exc:  # a missing app database, a fresh machine
        logger.debug("no snapshot history to size against: %s", exc)
        return None
    # There is no single `size_bytes`: a snapshot records three parts, and the
    # next one costs the sum of them.
    sizes = [
        int(s.duckdb_size_bytes or 0)
        + int(s.lance_size_bytes or 0)
        + int(s.files_size_bytes or 0)
        for s in snapshots
    ]
    sizes = [size for size in sizes if size > 0]
    return max(sizes) if sizes else None


def _library_bytes(library_path: Path) -> int:
    """The project's own size on disk, as the fallback snapshot estimate."""
    total = 0
    if library_path.is_file():
        return library_path.stat().st_size
    for path in library_path.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def estimate_space(db: Any, library_path: Path) -> tuple[int, int]:
    """``(required_bytes, available_bytes)`` — step 2.

    Required is the snapshot's likely size (the largest snapshot this library
    has had, or the project's own size when it has never had one) plus the new
    records, times :data:`DISK_MARGIN`.

    Deliberately pessimistic. Being too cautious costs a conversion that waits
    until the next open; being too optimistic costs a library that ran out of
    disk halfway through writing records, which is the state nobody chose.
    """
    snapshot_bytes = _last_snapshot_bytes(library_path) or _library_bytes(library_path)
    records_bytes = _boxes_to_convert(db) * BYTES_PER_BOX_ESTIMATE
    required = int((snapshot_bytes + records_bytes) * DISK_MARGIN)
    try:
        available = shutil.disk_usage(library_path).free
    except OSError as exc:
        raise ConversionPreflightFailed(
            f"could not read free space at {library_path}: {exc}"
        ) from exc
    return required, int(available)


def _live_row_counts(db: Any) -> dict[str, int]:
    """Every table in the project and its row count, for the snapshot proof."""
    try:
        tables = [r[0] for r in db.conn.execute("SHOW TABLES").fetchall()]
    except Exception as exc:
        raise ConversionPreflightFailed(f"could not list the project's tables: {exc}") from exc
    if not tables:
        raise ConversionPreflightFailed(
            "the project reports NO tables, which cannot be true of an open "
            "library — this check has gone blind rather than found an empty project"
        )
    counts: dict[str, int] = {}
    for table in tables:
        row = db.conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()
        counts[table] = int((row[0] if row else 0) or 0)
    return counts


def prove_snapshot(db: Any, snapshot: Any) -> dict[str, Any]:
    """Read the snapshot back and compare row counts, table by table.

    **The rule is "snapshot first, AND PROVED RESTORABLE" — so the snapshot
    having been written is not the check.** A snapshot is a promise about a bad
    day; the only way to know it is real is to open it and count. That is the
    same discipline that caught the missing indexes: assert against what is
    there, never against the fact that the code that should have made it
    returned without raising.

    Returns the proof: `{"tables": n, "rows": n, "mismatches": {...}}`. A
    non-empty `mismatches` means the caller must refuse — this function reports,
    it does not decide.
    """
    live = _live_row_counts(db)
    export_dir = Path(snapshot.snapshot_path) / Path(snapshot.duckdb_path).name
    if not export_dir.is_dir():
        # Try the documented layout directly; a snapshot whose exports are not
        # where its own record says they are is exactly what this proves.
        export_dir = Path(snapshot.snapshot_path) / "duckdb_export"
    if not export_dir.is_dir():
        return {
            "tables": 0,
            "rows": 0,
            "mismatches": {"__exports__": f"no exported tables at {export_dir}"},
        }

    mismatches: dict[str, Any] = {}
    proved_rows = 0
    for table, expected in sorted(live.items()):
        parquet = export_dir / f"{table}.parquet"
        if not parquet.is_file():
            if expected == 0:
                # An empty table the export skipped is not a discrepancy worth
                # refusing over: there is nothing in it to lose.
                continue
            mismatches[table] = {"expected": expected, "found": "no parquet file"}
            continue
        try:
            row = db.conn.execute(
                "SELECT count(*) FROM read_parquet(?)", [str(parquet)]
            ).fetchone()
        except Exception as exc:
            mismatches[table] = {"expected": expected, "found": f"unreadable: {exc}"}
            continue
        found = int((row[0] if row else 0) or 0)
        proved_rows += found
        if found != expected:
            mismatches[table] = {"expected": expected, "found": found}

    return {
        "tables": len(live),
        "rows": proved_rows,
        "mismatches": mismatches,
    }


def plan_conversion(db: Any, library_path: str | Path) -> ConversionRun | None:
    """Steps 1 to 3. Returns the run to proceed with, or a refusal, or None.

    `None` means **nothing to do, and nothing written** — not even a report
    row. That is what makes every later project open free, and it is the
    overwhelmingly common case once a library has been converted once.

    A returned run with verdict `ready` has a PROVED, PINNED snapshot and may
    convert pages. Any other verdict means nothing was converted and nothing is
    half done; the next open tries again.

    The caller saves the run. This function writes no report row itself, so a
    caller that wants to preflight without recording (a diagnostic, a dry run)
    can.
    """
    library_path = Path(library_path)
    started = utc_now()

    results, documents = conversion_scope(db)
    if results == 0:
        return None

    required, available = estimate_space(db, library_path)
    if available < required:
        logger.info(
            "project conversion refused: needs %d bytes with margin, %d free",
            required, available,
        )
        return ConversionRun(
            verdict=ConversionVerdict.refused_disk,
            started_at=started,
            finished_at=utc_now(),
            results_to_convert=results,
            documents_to_convert=documents,
            disk_required_bytes=required,
            disk_available_bytes=available,
        )

    run = ConversionRun(
        verdict=ConversionVerdict.ready,
        started_at=started,
        results_to_convert=results,
        documents_to_convert=documents,
        disk_required_bytes=required,
        disk_available_bytes=available,
    )

    try:
        from fichero_server.db.storage_snapshots import snapshot_library

        snapshot = snapshot_library(
            str(library_path),
            reason=(
                "before converting this project's stored geometry to segment "
                f"records (source model, run {run.run_id})"
            ),
            initiator="system",
            run_id=run.run_id,
        )
    except Exception as exc:
        logger.warning("project conversion refused: no snapshot (%s)", exc)
        run.verdict = ConversionVerdict.refused_snapshot
        run.finished_at = utc_now()
        run.snapshot_proof = {"mismatches": {"__snapshot__": str(exc)}}
        return run

    run.snapshot_id = snapshot.id
    run.snapshot_path = snapshot.snapshot_path
    _pin(snapshot)
    run.snapshot_proof = prove_snapshot(db, snapshot)
    if run.snapshot_proof.get("mismatches"):
        logger.warning(
            "project conversion refused: snapshot %s does not read back (%s)",
            snapshot.id, run.snapshot_proof["mismatches"],
        )
        run.verdict = ConversionVerdict.refused_snapshot
        run.finished_at = utc_now()
    return run


def _pin(snapshot: Any) -> None:
    """Keep this snapshot out of the retention tidy-up.

    CORRECTION to the build notes (2026-09-26): they say retention "would
    delete the pre-conversion snapshot if nothing stops it", implying a pin has
    to be built. It already exists — `_enforce_retention` skips `s.is_pinned`
    in BOTH its expiry pass and its keep-the-last-N pass. So this sets the flag
    that is already honoured rather than adding a second mechanism, which is
    how second paths start.

    There is no `pin_snapshot()` helper -- checked, not assumed: the flag lives
    on the record (`LibrarySnapshot.is_pinned`) and `_save_snapshot_record`
    persists it. Written through that rather than a new helper, because one
    caller does not earn an API.

    Best-effort by design: a snapshot that is proved but not pinned is still a
    way back, and refusing a conversion because a flag could not be written
    would be refusing over the bookkeeping rather than over the safety net.
    The report carries the snapshot id either way, so the way back is findable
    even if retention later tidies the record.
    """
    try:
        from fichero_server.db.storage_snapshots import _save_snapshot_record

        snapshot.is_pinned = True
        _save_snapshot_record(snapshot)
    except Exception as exc:
        logger.warning(
            "could not pin snapshot %s; it is still the way back, but retention "
            "may tidy it: %s", snapshot.id, exc,
        )


# ===========================================================================
# Part 2 — the page loop
#
# `source.convert.the-machine-stays-usable`, `.a-page-is-all-or-nothing`,
# `.stops-starts-and-repeats-safely`, `.only-the-running-engine`, `.report`.
#
# ONE PAGE AT A TIME, each page its own audited action in its own transaction:
# all of that page's results become passes, or none do. Never a whole project
# in one transaction — a project of twenty thousand pages in one transaction is
# the half-succeeded state this design exists to make impossible, dressed up as
# atomicity.
# ===========================================================================

#: The system's name in the audit chain for this work. A conversion is not a
#: person's edit and must never be recorded as one: every page's audit row says
#: the engine did it, and the pages' segments keep their own makers
#: (`source.store.converted-boxes-keep-their-maker`).
SYSTEM_ACTOR = "system"


def documents_to_convert(db: Any) -> list[str]:
    """Every document with an unconverted result, OLDEST FIRST.

    Oldest first because a person working through an archive starts at the
    beginning, so the pages they are most likely to open next are the ones
    already done. It is also stable: the same order on a resumed run, which is
    what lets "stop after page n and start again" end up somewhere a test can
    compare.
    """
    sql = """
        SELECT a.document_id, min(a.created_at) AS first_seen
        FROM artifacts a
        WHERE a.ocr_geometry IS NOT NULL
          AND a.geometry_superseded_by_pass_id IS NULL
          AND json_array_length(json_extract(a.ocr_geometry, '$.boxes')) > 0
        GROUP BY a.document_id
        ORDER BY first_seen, a.document_id
    """
    try:
        rows = db.conn.execute(sql).fetchall()
    except Exception as exc:
        message = str(exc).lower()
        if "artifacts" in message and ("not exist" in message or "catalog" in message):
            return []
        raise ConversionPreflightFailed(
            f"could not list the documents left to convert: {exc}"
        ) from exc
    return [row[0] for row in rows]


def _convert_one_page(db: Any, document_id: str, run_id: str) -> str:
    """Convert one page. Returns ``"converted"``, ``"skipped"``, or raises.

    The page action is invoked with `document_id` ALONE — its eager form, which
    converts and edits nothing. Not a second conversion path: the same action a
    person's first edit uses, so a page converted by the background runner and a
    page converted by an edit get the same ids, the same passes and the same
    audit shape. That is what makes "an edit gets ahead of the queue" true
    rather than approximately true.

    `AlreadyConverted` and `NothingToConvert` are NOT failures. They mean
    somebody got there ahead of the runner — an edit, or another result on the
    page — which is the design working, not something to report as a problem.
    """
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.api.routes.document.segment_conversion import (
        AlreadyConverted,
        NothingToConvert,
    )

    ctx = ActionContext(
        actor=SYSTEM_ACTOR,
        run_id=run_id,
        # The engine owns the project it has open, and this is the engine's own
        # background work rather than a request from anybody. `is_bootstrap`
        # says so to the action layer's authz gate; a per-user permission check
        # here would be asking whether the machine may act on its own data.
        is_bootstrap=True,
    )
    try:
        registry.invoke(db, "segment.convert_and_edit", {"document_id": document_id}, ctx)
    except (AlreadyConverted, NothingToConvert):
        return "skipped"
    return "converted"


#: How long an unfinished run may go untouched before another opening may take
#: it over. Generous on purpose: a page of a dense manuscript can take a while at
#: background priority, and stealing a lock from a runner that is merely slow
#: would start a second writer, which is the thing the lock exists to prevent.
#: The cost of waiting too long is a conversion that starts at the next open;
#: the cost of waiting too little is two runners.
STALE_HEARTBEAT_SECONDS = 600.0


class ConversionAlreadyRunning(RuntimeError):
    """Another opening of this project is already converting it.

    Not an error the caller should retry in a loop: the other runner will
    finish, and every later open finds nothing to do. Raised rather than
    returned so a caller cannot mistake it for "nothing to convert" — those two
    look identical from the outside and mean opposite things.
    """

    def __init__(self, run_id: str, heartbeat_at: Any) -> None:
        self.run_id = run_id
        super().__init__(
            f"conversion run {run_id} is already in progress "
            f"(last heartbeat {heartbeat_at})"
        )


def running_conversion(db: Any) -> ConversionRun | None:
    """The run another opening is working on, or None.

    "Another opening" and not "another thread": the rule is about a project
    being opened twice — a second app, or a remote client's engine — which is
    why the lock lives in the PROJECT's database rather than in memory.
    """
    now = utc_now()
    for run in db.query(ConversionRun):
        if not run.is_running:
            continue
        beat = run.heartbeat_at or run.started_at
        if (now - beat).total_seconds() <= STALE_HEARTBEAT_SECONDS:
            return run
    return None


def abandoned_conversions(db: Any) -> list[ConversionRun]:
    """Claims whose runner stopped without finishing — a force-quit, a crash.

    Left in the table rather than deleted. "The app was killed halfway through
    converting this project" is a fact about the library worth keeping, and it is
    the only evidence a person has that a conversion they started never ended.
    """
    now = utc_now()
    return [
        run
        for run in db.query(ConversionRun)
        if run.is_running
        and (now - (run.heartbeat_at or run.started_at)).total_seconds()
        > STALE_HEARTBEAT_SECONDS
    ]


def convert_project(
    db: Any,
    library_path: str | Path,
    *,
    should_stop: Any = None,
    on_page: Any = None,
) -> ConversionRun | None:
    """Convert a whole project, or say why it will not. Steps 1 to 5.

    Returns `None` when there was nothing to do — and writes nothing at all in
    that case, not even a report, which is what makes every later project open
    free.

    `should_stop` is a callable the engine passes to mean "shut down now, or a
    person is waiting". Checked BETWEEN pages, never inside one: a page is all
    or nothing, so the only safe place to stop is at a page boundary. Stopping
    is not a failure and not an error — the run is recorded as it stands and the
    next open carries on from the markers, because progress IS the markers.

    `on_page` is an optional per-page callback for progress reporting. It is a
    read-only side channel: whatever it does cannot affect the conversion, and
    an exception from it is logged and swallowed rather than being allowed to
    fail a page that in fact converted.

    **Never called at open, never from a migration, never from the CLI**
    (`source.convert.only-the-running-engine`). The engine that already has the
    project open starts this after the project has opened, and one project has
    one engine, so there is one runner.
    """
    library_path = Path(library_path)

    # The lock FIRST, before the snapshot: a second runner must not take a
    # snapshot of a project the first one is already converting.
    held = running_conversion(db)
    if held is not None:
        raise ConversionAlreadyRunning(held.run_id, held.heartbeat_at or held.started_at)
    for abandoned in abandoned_conversions(db):
        # Mark it as what it was, so the row stops being a lock and starts being
        # a record. `failed` rather than `completed`: nobody knows whether its
        # pages finished, and the markers -- not this row -- say what is left.
        logger.info(
            "taking over from run %s, abandoned without finishing", abandoned.run_id
        )
        db.save(
            abandoned.model_copy(
                update={
                    "verdict": ConversionVerdict.failed,
                    "finished_at": utc_now(),
                    "failures": [
                        *abandoned.failures,
                        ConversionFailure(
                            document_id="",
                            reason=(
                                "the runner stopped without finishing; a later "
                                "opening took over. What was converted is "
                                "recorded in the markers, not here."
                            ),
                        ),
                    ],
                }
            )
        )

    run = plan_conversion(db, library_path)
    if run is None:
        return None
    if run.verdict is not ConversionVerdict.ready:
        db.save(run)
        return run

    from fichero_server.core.background_compute import set_background_qos

    try:
        set_background_qos()
    except Exception as exc:
        # A missing QoS API is not a reason to refuse to convert; it is a reason
        # the machine will feel this more than it should, which is worth a line.
        logger.warning("could not lower this thread's priority: %s", exc)

    started = run.started_at
    run.heartbeat_at = utc_now()
    db.save(run)

    for document_id in documents_to_convert(db):
        if should_stop is not None and should_stop():
            logger.info("project conversion stopping at a page boundary, as asked")
            break
        try:
            outcome = _convert_one_page(db, document_id, run.run_id)
        except Exception as exc:
            # A page that cannot convert is RECORDED AND SKIPPED. It does not
            # stop the others, and it still reads from its block exactly as
            # before, so the library is not worse for the failure.
            run.failures.append(
                ConversionFailure(document_id=document_id, reason=str(exc))
            )
            logger.warning("page %s could not convert: %s", document_id, exc)
        else:
            if outcome == "converted":
                run.pages_converted += 1
            else:
                run.pages_skipped += 1
        # Stamped per page, the same boundary everything else here uses. This
        # is what keeps the lock held while the work is real, and what lets a
        # later opening tell "working" from "abandoned".
        run.heartbeat_at = utc_now()
        db.save(run)
        if on_page is not None:
            try:
                on_page(run)
            except Exception as exc:
                logger.debug("conversion progress callback raised: %s", exc)

    run.verdict = ConversionVerdict.completed
    run.finished_at = utc_now()
    run.seconds = (run.finished_at - started).total_seconds()
    db.save(run)
    logger.info(
        "project conversion finished: %d converted, %d skipped, %d failed in %.1fs",
        run.pages_converted, run.pages_skipped, len(run.failures), run.seconds,
    )
    return run
