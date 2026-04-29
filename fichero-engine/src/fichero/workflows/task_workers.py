"""Task worker implementations — mixin for TaskQueue.

Each task type has two methods:
  _execute_<type>: public entry for direct calls (claims + runs + finalizes)
  _do_<type>: internal implementation (called by both direct and scheduler paths)

Assumes mixed into TaskQueue which provides: self.database, self._save_task,
self._executing, self._tasks.
"""

import asyncio
import logging
from datetime import datetime

from fichero.knowledge_models import KnowledgeClaim, KnowledgeClaimLink, KnowledgeEntity
from fichero.models import Artifact, Document

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

    async def _execute_reindex(self, task: BackgroundTask) -> TaskResult:
        """Public entry point for reindex — claims task, runs, finalizes."""
        claimed = await self._claim_for_direct_execution(task)
        if not claimed:
            return task.result or TaskResult(success=True, message="Already executing")
        try:
            result = await self._do_reindex(task)
            task.completed_at = datetime.now()
            await self._save_task(task)
            return result
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.result = TaskResult(success=False, message="Task failed", error=str(e))
            task.completed_at = datetime.now()
            await self._save_task(task)
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
        docs = await asyncio.to_thread(self.database.all, Document)
        total = len(docs)

        task.progress.total = total
        task.progress.message = f"Reindexing {total} documents..."
        await self._save_task(task)

        indexed = 0
        for i, doc in enumerate(docs):
            try:
                # Skip documents without content
                if not doc.page_content:
                    continue

                # Embed document
                success = await asyncio.to_thread(self.database.embed, doc)
                if success:
                    indexed += 1

                # Update progress every 10 documents or on last
                if (i + 1) % 10 == 0 or i == total - 1:
                    task.progress.current = i + 1
                    task.progress.percent = ((i + 1) / total) * 100
                    task.progress.message = f"Indexed {indexed}/{i + 1} documents"
                    task.progress.updated_at = datetime.now()
                    await self._save_task(task)

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
            result = await self._do_metrics(task)
            task.completed_at = datetime.now()
            await self._save_task(task)
            return result
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.result = TaskResult(success=False, message="Task failed", error=str(e))
            task.completed_at = datetime.now()
            await self._save_task(task)
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
        await self._save_task(task)

        # Step 1: Document counts
        task.progress.current = 1
        task.progress.message = "Counting documents..."
        task.progress.percent = 20.0
        await self._save_task(task)

        docs = await asyncio.to_thread(self.database.all, Document)
        doc_count = len(docs)

        # Step 2: Embedding stats
        task.progress.current = 2
        task.progress.message = "Getting embedding stats..."
        task.progress.percent = 40.0
        await self._save_task(task)

        stats = await asyncio.to_thread(self.database.embedding_stats)

        # Step 3: File type distribution
        task.progress.current = 3
        task.progress.message = "Analyzing file types..."
        task.progress.percent = 60.0
        await self._save_task(task)

        file_types: dict[str, int] = {}
        for doc in docs:
            ft = doc.file_type.value if doc.file_type else "unknown"
            file_types[ft] = file_types.get(ft, 0) + 1

        # Step 4: Status distribution
        task.progress.current = 4
        task.progress.message = "Analyzing document status..."
        task.progress.percent = 80.0
        await self._save_task(task)

        status_counts: dict[str, int] = {}
        for doc in docs:
            st = doc.status.value if doc.status else "unknown"
            status_counts[st] = status_counts.get(st, 0) + 1

        # Step 5: Complete
        task.progress.current = 5
        task.progress.message = "Metrics computed"
        task.progress.percent = 100.0
        await self._save_task(task)

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
            result = await self._do_repair(task)
            task.completed_at = datetime.now()
            await self._save_task(task)
            return result
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.result = TaskResult(success=False, message="Task failed", error=str(e))
            task.completed_at = datetime.now()
            await self._save_task(task)
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
        await self._save_task(task)

        repaired = {"embeddings": 0, "artifacts": 0, "docs": 0}

        # Step 1: Check for documents missing embeddings
        task.progress.current = 1
        task.progress.message = "Checking document embeddings..."
        task.progress.percent = 33.3
        await self._save_task(task)

        docs = await asyncio.to_thread(self.database.all, Document)
        for doc in docs:
            if doc.page_content and not getattr(doc, "embedding", None):
                try:
                    await asyncio.to_thread(self.database.embed, doc)
                    repaired["embeddings"] += 1
                except Exception as e:
                    logger.warning(f"Failed to embed document {doc.id}: {e}")

        # Step 2: Check for orphaned artifacts
        task.progress.current = 2
        task.progress.message = "Checking for orphaned artifacts..."
        task.progress.percent = 66.6
        await self._save_task(task)

        artifacts = await asyncio.to_thread(self.database.all, Artifact)
        doc_ids = {d.id for d in docs}
        for artifact in artifacts:
            artifact_doc_id = getattr(artifact, "document_id", None)
            if artifact_doc_id and artifact_doc_id not in doc_ids:
                # Orphaned artifact - delete or mark as orphaned
                await asyncio.to_thread(self.database.delete, artifact)
                repaired["artifacts"] += 1

        # Step 3: Validate document metadata
        task.progress.current = 3
        task.progress.message = "Validating document metadata..."
        task.progress.percent = 100.0
        await self._save_task(task)

        for doc in docs:
            needs_save = False
            if not doc.updated_at:
                doc.updated_at = datetime.now()
                needs_save = True
            if not doc.created_at:
                doc.created_at = datetime.now()
                needs_save = True
            if needs_save:
                await asyncio.to_thread(self.database.save, doc)
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
            result = await self._do_vector_repair(task)
            task.completed_at = datetime.now()
            await self._save_task(task)
            return result
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.result = TaskResult(success=False, message="Task failed", error=str(e))
            task.completed_at = datetime.now()
            await self._save_task(task)
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
        await self._save_task(task)

        repaired = {"added": 0, "removed": 0, "checked": 0}

        # Step 1: Get all documents and their vector status
        task.progress.current = 1
        task.progress.message = "Scanning documents..."
        task.progress.percent = 25.0
        await self._save_task(task)

        docs = await asyncio.to_thread(self.database.all, Document)

        # Step 2: Check for documents needing embeddings
        task.progress.current = 2
        task.progress.message = "Checking embeddings..."
        task.progress.percent = 50.0
        await self._save_task(task)

        for doc in docs:
            if doc.page_content and not getattr(doc, "embedding", None):
                try:
                    success = await asyncio.to_thread(self.database.embed, doc)
                    if success:
                        repaired["added"] += 1
                except Exception as e:
                    logger.warning(f"Failed to repair embedding for {doc.id}: {e}")
            repaired["checked"] += 1

        # Step 3: Validate LanceDB table consistency
        task.progress.current = 3
        task.progress.message = "Validating LanceDB table..."
        task.progress.percent = 75.0
        await self._save_task(task)

        vector_count = 0
        try:
            stats = await asyncio.to_thread(self.database.embedding_stats)
            vector_count = stats.get("total_vectors", 0)
        except Exception as e:
            logger.warning(f"Could not get embedding stats: {e}")

        # Step 4: Complete
        task.progress.current = 4
        task.progress.message = "Vector repair complete"
        task.progress.percent = 100.0
        await self._save_task(task)

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
            result = await self._do_kg_metrics(task)
            task.completed_at = datetime.now()
            await self._save_task(task)
            return result
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.result = TaskResult(success=False, message="Task failed", error=str(e))
            task.completed_at = datetime.now()
            await self._save_task(task)
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
        await self._save_task(task)

        # Step 1: Entity metrics
        task.progress.current = 1
        task.progress.message = "Computing entity metrics..."
        task.progress.percent = 25.0
        await self._save_task(task)

        entities = await asyncio.to_thread(self.database.all, KnowledgeEntity)
        entity_by_type: dict[str, int] = {}
        for ent in entities:
            et = ent.entity_type.value if ent.entity_type else "unknown"
            entity_by_type[et] = entity_by_type.get(et, 0) + 1

        # Step 2: Claim metrics
        task.progress.current = 2
        task.progress.message = "Computing claim metrics..."
        task.progress.percent = 50.0
        await self._save_task(task)

        claims = await asyncio.to_thread(self.database.all, KnowledgeClaim)
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
        await self._save_task(task)

        links = await asyncio.to_thread(self.database.all, KnowledgeClaimLink)
        links_by_relation: dict[str, int] = {}
        for link in links:
            rt = link.relation_type.value if link.relation_type else "unknown"
            links_by_relation[rt] = links_by_relation.get(rt, 0) + 1

        # Step 4: Complete
        task.progress.current = 4
        task.progress.message = "Knowledge graph metrics computed"
        task.progress.percent = 100.0
        await self._save_task(task)

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
