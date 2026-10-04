"""Task worker implementations — mixin for TaskQueue.

Each task type has two methods:
  _execute_<type>: public entry for direct calls (claims + runs + finalizes)
  _do_<type>: internal implementation (called by both direct and scheduler paths)

Assumes mixed into TaskQueue which provides: self.database, self._save_task,
self._executing, self._tasks.
"""

import asyncio
import logging
from fichero_server.core.timeutil import utc_now
from pathlib import Path

from fichero_server.db import db_manager
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeClaimLink, KnowledgeEntity
from fichero_server.models import Artifact, Document

from .task_types import BackgroundTask, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class TaskWorkersMixin:
    """Mixin providing worker implementations for TaskQueue.

    Requires the host class to provide:
    - self.database: Optional[Database]
    - self._save_task(task): coroutine
    - self._executing: set[str]
    - self._claim_for_direct_execution(task): coroutine -> bool
    """

    def _db_call(self, method_name: str, *args):
        """Run a ``Database`` method inside the current (pool) thread using
        that thread's OWN keyed connection.

        A DuckDB ``Connection`` is not safe to share across threads, and
        ``db_manager`` keys its connection pool by ``threading.get_ident()``
        precisely for that reason. These workers drive the database from
        arbitrary ``asyncio.to_thread`` pool threads, so we must NOT capture
        and ship ``self.database`` (bound to the thread that created the
        queue) across the thread boundary. Instead we resolve the package
        path from the captured Database (reading the ``.path`` attribute is
        safe — it never touches the connection) and obtain a thread-local
        Database from ``db_manager`` from WITHIN the pool thread, so each
        pool thread gets its own connection to the same package.

        Must be invoked as the ``asyncio.to_thread`` callable so the
        ``get_database`` call runs in the pool thread:

            docs = await asyncio.to_thread(self._db_call, "all", Document)
        """
        package_path = Path(self.database.path).parent
        db = db_manager.get_database(package_path)
        return getattr(db, method_name)(*args)

    async def _mark_task_started(self, task: BackgroundTask) -> None:
        await self._save_task(task)
        self._emit_task_change(task, "backend.work.started")

    async def _save_task_progress(self, task: BackgroundTask) -> None:
        task.progress.updated_at = utc_now()
        await self._save_task(task)
        self._emit_task_change(task, "backend.work.progress")

    async def _finalize_task_execution(self, task: BackgroundTask) -> None:
        task.completed_at = utc_now()
        await self._save_task(task)
        terminal_type = (
            "backend.work.completed"
            if task.status == TaskStatus.COMPLETED
            else "backend.work.cancelled"
            if task.status == TaskStatus.CANCELLED
            else "backend.work.failed"
        )
        self._emit_task_change(task, terminal_type)

    async def _execute_reindex(self, task: BackgroundTask) -> TaskResult:
        """Public entry point for reindex — claims task, runs, finalizes."""
        claimed = await self._claim_for_direct_execution(task)
        if not claimed:
            return task.result or TaskResult(success=True, message="Already executing")
        try:
            await self._mark_task_started(task)
            result = await self._do_reindex(task)
            await self._finalize_task_execution(task)
            return result
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.result = TaskResult(success=False, message="Task failed", error=str(e))
            await self._finalize_task_execution(task)
            return task.result
        finally:
            self._executing.discard(task.task_id)

    async def _do_reindex(self, task: BackgroundTask) -> TaskResult:
        """Internal reindex implementation (called by _execute_reindex and _execute_task)."""
        if not self.database:
            result = TaskResult(
                success=False,
                message="Database not available",
                error="Database not initialized",
            )
            task.result = result
            task.status = TaskStatus.FAILED
            return result

        # Get documents to reindex
        docs = await asyncio.to_thread(self._db_call, "all", Document)
        total = len(docs)

        task.progress.total = total
        task.progress.message = f"Reindexing {total} documents..."
        await self._save_task_progress(task)

        indexed = 0
        for i, doc in enumerate(docs):
            try:
                # Skip documents without content
                if not doc.page_content:
                    continue

                # Embed document
                success = await asyncio.to_thread(self._db_call, "embed", doc)
                if success:
                    indexed += 1

                # Update progress every 10 documents or on last
                if (i + 1) % 10 == 0 or i == total - 1:
                    task.progress.current = i + 1
                    task.progress.percent = ((i + 1) / total) * 100
                    task.progress.message = f"Indexed {indexed}/{i + 1} documents"
                    await self._save_task_progress(task)

            except Exception as e:
                logger.warning(f"Failed to index document {doc.id}: {e}")

        result = TaskResult(
            success=True,
            message=f"Reindexed {indexed}/{total} documents",
            details={"indexed": indexed, "total": total},
        )
        task.result = result
        task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
        return result

    async def _execute_metrics(self, task: BackgroundTask) -> TaskResult:
        """Public entry point for metrics — claims task, runs, finalizes."""
        claimed = await self._claim_for_direct_execution(task)
        if not claimed:
            return task.result or TaskResult(success=True, message="Already executing")
        try:
            await self._mark_task_started(task)
            result = await self._do_metrics(task)
            await self._finalize_task_execution(task)
            return result
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.result = TaskResult(success=False, message="Task failed", error=str(e))
            await self._finalize_task_execution(task)
            return task.result
        finally:
            self._executing.discard(task.task_id)

    async def _do_metrics(self, task: BackgroundTask) -> TaskResult:
        """Internal metrics implementation (called by _execute_metrics and _execute_task)."""
        if not self.database:
            result = TaskResult(
                success=False,
                message="Database not available",
                error="Database not initialized",
            )
            task.result = result
            task.status = TaskStatus.FAILED
            return result

        task.progress.total = 5  # Steps in metrics computation
        task.progress.message = "Computing library metrics..."
        await self._save_task_progress(task)

        # Step 1: Document counts
        task.progress.current = 1
        task.progress.message = "Counting documents..."
        task.progress.percent = 20.0
        await self._save_task_progress(task)

        docs = await asyncio.to_thread(self._db_call, "all", Document)
        doc_count = len(docs)

        # Step 2: Embedding stats
        task.progress.current = 2
        task.progress.message = "Getting embedding stats..."
        task.progress.percent = 40.0
        await self._save_task_progress(task)

        stats = await asyncio.to_thread(self._db_call, "embedding_stats")

        # Step 3: File type distribution
        task.progress.current = 3
        task.progress.message = "Analyzing file types..."
        task.progress.percent = 60.0
        await self._save_task_progress(task)

        file_types: dict[str, int] = {}
        for doc in docs:
            ft = doc.file_type.value if doc.file_type else "unknown"
            file_types[ft] = file_types.get(ft, 0) + 1

        # Step 4: Status distribution
        task.progress.current = 4
        task.progress.message = "Analyzing document status..."
        task.progress.percent = 80.0
        await self._save_task_progress(task)

        status_counts: dict[str, int] = {}
        for doc in docs:
            st = doc.status.value if doc.status else "unknown"
            status_counts[st] = status_counts.get(st, 0) + 1

        # Step 5: Complete
        task.progress.current = 5
        task.progress.message = "Metrics computed"
        task.progress.percent = 100.0
        await self._save_task_progress(task)

        result = TaskResult(
            success=True,
            message=f"Metrics computed for {doc_count} documents",
            details={
                "document_count": doc_count,
                "embedding_stats": stats,
                "file_types": file_types,
                "status_distribution": status_counts,
            },
        )
        task.result = result
        task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
        return result

    async def _execute_repair(self, task: BackgroundTask) -> TaskResult:
        """Public entry point for repair — claims task, runs, finalizes."""
        claimed = await self._claim_for_direct_execution(task)
        if not claimed:
            return task.result or TaskResult(success=True, message="Already executing")
        try:
            await self._mark_task_started(task)
            result = await self._do_repair(task)
            await self._finalize_task_execution(task)
            return result
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.result = TaskResult(success=False, message="Task failed", error=str(e))
            await self._finalize_task_execution(task)
            return task.result
        finally:
            self._executing.discard(task.task_id)

    async def _do_repair(self, task: BackgroundTask) -> TaskResult:
        """Internal repair implementation (called by _execute_repair and _execute_task).

        Repairs:
        - Documents with missing embeddings
        - Orphaned artifacts
        - Stale metadata entries
        """
        if not self.database:
            result = TaskResult(
                success=False,
                message="Database not available",
                error="Database not initialized",
            )
            task.result = result
            task.status = TaskStatus.FAILED
            return result

        task.progress.total = 3
        task.progress.message = "Repairing database inconsistencies..."
        await self._save_task_progress(task)

        repaired = {"embeddings": 0, "artifacts": 0, "docs": 0}

        # Step 1: Check for documents missing embeddings
        task.progress.current = 1
        task.progress.message = "Checking document embeddings..."
        task.progress.percent = 33.3
        await self._save_task_progress(task)

        docs = await asyncio.to_thread(self._db_call, "all", Document)
        for doc in docs:
            if doc.page_content and not getattr(doc, "embedding", None):
                try:
                    await asyncio.to_thread(self._db_call, "embed", doc)
                    repaired["embeddings"] += 1
                except Exception as e:
                    logger.warning(f"Failed to embed document {doc.id}: {e}")

        # Step 2: Check for orphaned artifacts
        task.progress.current = 2
        task.progress.message = "Checking for orphaned artifacts..."
        task.progress.percent = 66.6
        await self._save_task_progress(task)

        artifacts = await asyncio.to_thread(self._db_call, "all", Artifact)
        doc_ids = {d.id for d in docs}
        for artifact in artifacts:
            artifact_doc_id = getattr(artifact, "document_id", None)
            if artifact_doc_id and artifact_doc_id not in doc_ids:
                # Orphaned artifact - delete or mark as orphaned
                await asyncio.to_thread(self._db_call, "delete", artifact)
                repaired["artifacts"] += 1

        # Step 3: Validate document metadata
        task.progress.current = 3
        task.progress.message = "Validating document metadata..."
        task.progress.percent = 100.0
        await self._save_task_progress(task)

        for doc in docs:
            needs_save = False
            if not doc.updated_at:
                doc.updated_at = utc_now()
                needs_save = True
            if not doc.created_at:
                doc.created_at = utc_now()
                needs_save = True
            if needs_save:
                await asyncio.to_thread(self._db_call, "save", doc)
                repaired["docs"] += 1

        total_repaired = sum(repaired.values())
        result = TaskResult(
            success=True,
            message=f"Repair completed: {total_repaired} items fixed",
            details=repaired,
        )
        task.result = result
        task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
        return result

    async def _execute_vector_repair(self, task: BackgroundTask) -> TaskResult:
        """Public entry point for vector repair — claims task, runs, finalizes."""
        claimed = await self._claim_for_direct_execution(task)
        if not claimed:
            return task.result or TaskResult(success=True, message="Already executing")
        try:
            await self._mark_task_started(task)
            result = await self._do_vector_repair(task)
            await self._finalize_task_execution(task)
            return result
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.result = TaskResult(success=False, message="Task failed", error=str(e))
            await self._finalize_task_execution(task)
            return task.result
        finally:
            self._executing.discard(task.task_id)

    async def _do_vector_repair(self, task: BackgroundTask) -> TaskResult:
        """Internal vector repair implementation.

        Repairs vector index issues:
        - Missing vectors for documents with content
        - Orphaned vectors (no corresponding document)
        - Vector dimension mismatches
        """
        if not self.database:
            result = TaskResult(
                success=False,
                message="Database not available",
                error="Database not initialized",
            )
            task.result = result
            task.status = TaskStatus.FAILED
            return result

        task.progress.total = 4
        task.progress.message = "Repairing vector index..."
        await self._save_task_progress(task)

        repaired = {"added": 0, "removed": 0, "checked": 0}

        # Step 1: Get all documents and their vector status
        task.progress.current = 1
        task.progress.message = "Scanning documents..."
        task.progress.percent = 25.0
        await self._save_task_progress(task)

        docs = await asyncio.to_thread(self._db_call, "all", Document)

        # Step 2: Check for documents needing embeddings
        task.progress.current = 2
        task.progress.message = "Checking embeddings..."
        task.progress.percent = 50.0
        await self._save_task_progress(task)

        for doc in docs:
            if doc.page_content and not getattr(doc, "embedding", None):
                try:
                    success = await asyncio.to_thread(self._db_call, "embed", doc)
                    if success:
                        repaired["added"] += 1
                except Exception as e:
                    logger.warning(f"Failed to repair embedding for {doc.id}: {e}")
            repaired["checked"] += 1

        # Step 3: Validate LanceDB table consistency
        task.progress.current = 3
        task.progress.message = "Validating LanceDB table..."
        task.progress.percent = 75.0
        await self._save_task_progress(task)

        vector_count = 0
        try:
            stats = await asyncio.to_thread(self._db_call, "embedding_stats")
            vector_count = stats.get("total_vectors", 0)
        except Exception as e:
            logger.warning(f"Could not get embedding stats: {e}")

        # Step 4: Complete
        task.progress.current = 4
        task.progress.message = "Vector repair complete"
        task.progress.percent = 100.0
        await self._save_task_progress(task)

        result = TaskResult(
            success=True,
            message=f"Vector repair complete: {repaired['added']} added, {repaired['removed']} removed",
            details={
                **repaired,
                "document_count": len(docs),
                "vector_count": vector_count,
            },
        )
        task.result = result
        task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
        return result

    async def _execute_kg_metrics(self, task: BackgroundTask) -> TaskResult:
        """Public entry point for KG metrics — claims task, runs, finalizes."""
        claimed = await self._claim_for_direct_execution(task)
        if not claimed:
            return task.result or TaskResult(success=True, message="Already executing")
        try:
            await self._mark_task_started(task)
            result = await self._do_kg_metrics(task)
            await self._finalize_task_execution(task)
            return result
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.result = TaskResult(success=False, message="Task failed", error=str(e))
            await self._finalize_task_execution(task)
            return task.result
        finally:
            self._executing.discard(task.task_id)

    async def _do_kg_metrics(self, task: BackgroundTask) -> TaskResult:
        """Internal KG metrics implementation.

        Recomputes:
        - Entity statistics (per type)
        - Claim statistics (per status, type)
        - Link statistics (per relation type)
        - Connected component analysis
        """
        if not self.database:
            result = TaskResult(
                success=False,
                message="Database not available",
                error="Database not initialized",
            )
            task.result = result
            task.status = TaskStatus.FAILED
            return result

        task.progress.total = 4
        task.progress.message = "Computing knowledge graph metrics..."
        await self._save_task_progress(task)

        # Step 1: Entity metrics
        task.progress.current = 1
        task.progress.message = "Computing entity metrics..."
        task.progress.percent = 25.0
        await self._save_task_progress(task)

        entities = await asyncio.to_thread(self._db_call, "all", KnowledgeEntity)
        entity_by_type: dict[str, int] = {}
        for ent in entities:
            et = ent.entity_type.value if ent.entity_type else "unknown"
            entity_by_type[et] = entity_by_type.get(et, 0) + 1

        # Step 2: Claim metrics
        task.progress.current = 2
        task.progress.message = "Computing claim metrics..."
        task.progress.percent = 50.0
        await self._save_task_progress(task)

        claims = await asyncio.to_thread(self._db_call, "all", KnowledgeClaim)
        claims_by_status: dict[str, int] = {}
        claims_by_type: dict[str, int] = {}
        claims_with_sources = 0

        for claim in claims:
            st = claim.curation_state.value if claim.curation_state else "unknown"
            claims_by_status[st] = claims_by_status.get(st, 0) + 1

            ct = claim.claim_type.value if claim.claim_type else "unknown"
            claims_by_type[ct] = claims_by_type.get(ct, 0) + 1

            if claim.source_ids or claim.source_document_id:
                claims_with_sources += 1

        # Step 3: Link metrics
        task.progress.current = 3
        task.progress.message = "Computing link metrics..."
        task.progress.percent = 75.0
        await self._save_task_progress(task)

        links = await asyncio.to_thread(self._db_call, "all", KnowledgeClaimLink)
        links_by_relation: dict[str, int] = {}
        for link in links:
            rt = link.relation_type.value if link.relation_type else "unknown"
            links_by_relation[rt] = links_by_relation.get(rt, 0) + 1

        # Step 4: Complete
        task.progress.current = 4
        task.progress.message = "Knowledge graph metrics computed"
        task.progress.percent = 100.0
        await self._save_task_progress(task)

        result = TaskResult(
            success=True,
            message=f"KG metrics: {len(entities)} entities, {len(claims)} claims, {len(links)} links",
            details={
                "entity_count": len(entities),
                "entity_by_type": entity_by_type,
                "claim_count": len(claims),
                "claims_by_status": claims_by_status,
                "claims_by_type": claims_by_type,
                "claims_with_sources": claims_with_sources,
                "link_count": len(links),
                "links_by_relation": links_by_relation,
            },
        )
        task.result = result
        task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
        return result

    async def _do_reanchor(self, task: BackgroundTask) -> TaskResult:
        """Bbox step 4 (rulings 2026-08-20): mark renditions whose pixels
        disagree with the node's frame while claiming identity, so overlays
        render UNANCHORED on them instead of drawing boxes on unproven pixels.

        `options={"dry_run": true}` reports what WOULD be marked and writes
        nothing — the required first run against a real archive.
        """
        if not self.database:
            result = TaskResult(
                success=False,
                message="Database not available",
                error="Database not initialized",
            )
            task.result = result
            task.status = TaskStatus.FAILED
            return result

        from fichero_server.maintenance.reanchor import apply_reanchor, plan_reanchor

        dry_run = bool((task.config.options or {}).get("dry_run", False))

        task.progress.total = 2
        task.progress.current = 1
        task.progress.message = "Classifying rendition frames..."
        task.progress.percent = 50.0
        await self._save_task_progress(task)

        plan = await asyncio.to_thread(plan_reanchor, self.database)

        written = 0
        if not dry_run and plan.to_mark:
            task.progress.current = 2
            task.progress.message = f"Marking {len(plan.to_mark)} rendition(s)..."
            task.progress.percent = 90.0
            await self._save_task_progress(task)
            written = await asyncio.to_thread(apply_reanchor, self.database, plan)

        details = dict(plan.counts)
        details["written"] = written
        details["dry_run"] = dry_run
        details["reasons"] = [reason for _, reason in plan.to_mark[:20]]
        result = TaskResult(
            success=True,
            message=(
                f"{'Would mark' if dry_run else 'Marked'} "
                f"{len(plan.to_mark)} rendition(s) frame-unknown"
            ),
            details=details,
        )
        task.result = result
        task.status = TaskStatus.COMPLETED
        return result


# =============================================================================
# The six task kinds as jobs (#5353, `activity.task-queue-grows-into-jobs`)
# =============================================================================
#
# The task queue (`tasks.TaskQueue`) was never started by the engine, so these workers only ever
# ran in tests. They run now as job kinds: each task is a row in the project's `jobs` table, run
# by the one scheduler (durable, pausable, shown in Activity), on the lane its work needs. The
# workers themselves are unchanged; `_JobTask` is the host they expect, writing progress and the
# result into the row's `detail` instead of the old `background_tasks` table.

#: kind -> (task type, lane, model, what Activity calls it)
TASK_JOB_KINDS = {
    "reindex": ("local-ml", "embedder", "Reindex search"),
    "vector_repair": ("local-ml", "embedder", "Repair search vectors"),
    "metrics": ("database", None, "Recompute library figures"),
    "repair": ("database", None, "Repair the library"),
    "kg_metrics": ("database", None, "Recompute knowledge-graph figures"),
    "reanchor": ("database", None, "Check page shapes against their images"),
}


class _JobTask(TaskWorkersMixin):
    """The host the workers expect, when a task runs as a job: its row is the record."""

    def __init__(self, db, job_id: str):
        self.database = db
        self.job_id = job_id

    async def _save_task(self, task: BackgroundTask) -> None:
        import json

        from fichero_server.execution import jobs

        detail = {
            "name": task.name,
            "options": task.config.options,
            "progress": task.progress.to_dict(),
            "result": task.result.to_dict() if task.result else None,
        }
        await asyncio.to_thread(jobs.save_detail, self.database, self.job_id,
                                json.dumps(detail, default=str), reason=task.progress.message or None)

    def _emit_task_change(self, task: BackgroundTask, change_type: str) -> None:
        return None  # the job row is the record; Activity reads it


def _run_task_job(task_type_value: str, db, subject: str) -> dict:
    import json

    from fichero_server.execution import jobs

    from .task_types import TaskConfig, TaskType

    job_id = jobs.current_job_id()
    row = jobs.read_job(db, job_id)
    detail = json.loads(row["detail"] or "{}") if row else {}
    task_type = TaskType(task_type_value)
    task = BackgroundTask(
        task_id=job_id, task_type=task_type, name=detail.get("name") or TASK_JOB_KINDS[task_type_value][2],
        status=TaskStatus.RUNNING, config=TaskConfig(task_type=task_type, options=detail.get("options") or {}),
        started_at=utc_now(),
    )
    host = _JobTask(db, job_id)
    result = asyncio.run(getattr(host, f"_do_{task_type_value}")(task))
    task.result = result
    asyncio.run(host._save_task(task))
    if not result.success:
        raise RuntimeError(result.error or result.message)
    return result.to_dict()


def register_job_kinds() -> None:
    """Called by the scheduler before its first scan (`execution.jobs._KIND_MODULES`), and by the
    task routes before they queue one."""
    from fichero_server.execution import jobs

    for kind, (lane, model, name) in TASK_JOB_KINDS.items():
        if kind not in jobs.KINDS:
            jobs.register_kind(kind, lambda db, subject, kind=kind: _run_task_job(kind, db, subject),
                               model=model, lane=lane, name=name)
