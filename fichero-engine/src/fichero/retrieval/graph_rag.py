from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from fichero.knowledge_models import KnowledgeClaim, KnowledgeEntity
from fichero.models import Document


@dataclass
class RetrievalPayload:
    context_docs: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    kg_claims_used: int = 0
    kg_entities_used: int = 0


class GraphAwareRetriever:
    """Shared retrieval engine for chat/researcher graph-RAG."""

    def __init__(self, db, file_reader: Callable[[str | None], str | None] | None = None):
        self.db = db
        self._file_reader = file_reader

    def retrieve(
        self,
        *,
        query: str,
        max_sources: int,
        include_sources: bool = True,
        document_ids: list[str] | None = None,
        graph_hops: int = 1,
        max_kg_claims: int = 12,
        search_type: str = "hybrid",
        filters: dict[str, Any] | None = None,
        min_score: float = 0.0,
    ) -> RetrievalPayload:
        payload = RetrievalPayload()
        content_by_doc_id: dict[str, str] = {}
        seed_doc_ids: list[str] = []

        if document_ids:
            for doc_id in document_ids[:max_sources]:
                doc = self.db.get(Document, doc_id)
                if doc is None:
                    continue
                content = self._read_content(doc)
                if not content:
                    continue
                seed_doc_ids.append(doc.id)
                content_by_doc_id[doc.id] = content
                payload.context_docs.append(
                    {
                        "id": doc.id,
                        "name": doc.name,
                        "content": content,
                        "kind": "document",
                        "search_score": 1.0,
                    }
                )
                if include_sources:
                    payload.sources.append(
                        {
                            "document_id": doc.id,
                            "document_name": doc.name,
                            "excerpt": self._excerpt(content),
                            "relevance_score": 1.0,
                        }
                    )
        else:
            search_results, _, _ = self.db.search(
                query=query,
                limit=max_sources,
                min_score=min_score,
                search_type=search_type,
                filters=filters or {},
            )
            for result in search_results:
                doc = self.db.get(Document, result.document_id)
                if doc is None:
                    continue
                content = self._read_content(doc)
                if not content:
                    continue
                seed_doc_ids.append(doc.id)
                content_by_doc_id[doc.id] = content
                payload.context_docs.append(
                    {
                        "id": doc.id,
                        "name": doc.name,
                        "content": content,
                        "kind": "document",
                        "search_score": result.score,
                    }
                )
                if include_sources:
                    payload.sources.append(
                        {
                            "document_id": doc.id,
                            "document_name": doc.name,
                            "excerpt": self._excerpt(content),
                            "relevance_score": result.score,
                        }
                    )

        if not seed_doc_ids:
            return payload

        self._augment_with_kg(
            payload=payload,
            seed_doc_ids=seed_doc_ids,
            content_by_doc_id=content_by_doc_id,
            graph_hops=graph_hops,
            max_kg_claims=max_kg_claims,
        )
        return payload

    def _augment_with_kg(
        self,
        *,
        payload: RetrievalPayload,
        seed_doc_ids: list[str],
        content_by_doc_id: dict[str, str],
        graph_hops: int,
        max_kg_claims: int,
    ) -> None:
        # --- Bounded KG augmentation (#3241) ---
        # Instead of loading the ENTIRE knowledge graph, we:
        # 1. Seed claims by source_document_id (filtered query)
        # 2. Expand per hop using claim↔entity intersection (filtered query)
        # 3. Cap gathered_claim_ids at 10× max_kg_claims to prevent
        #    hub entities from pulling the whole graph
        # 4. Fetch only referenced entities (single IN query)

        if not seed_doc_ids:
            return

        # Seed claims: query by source_document_id instead of full-table scan
        seed_claims = self.db.query(KnowledgeClaim, source_document_id=seed_doc_ids[0]) if len(seed_doc_ids) == 1 else [
            c for c in self.db.query(KnowledgeClaim)
            if c.source_document_id in seed_doc_ids
            or any(sid in seed_doc_ids for sid in (c.source_ids or []))
        ]
        if not seed_claims:
            return

        # Build lookup maps only for seed claims
        claim_by_id = {claim.id: claim for claim in seed_claims}
        seed_claim_ids = set(claim_by_id.keys())

        # Collect all entity IDs referenced by seed claims for first fetch
        seed_entity_ids: set[str] = set()
        for claim in seed_claims:
            for eid in (claim.entity_ids or []):
                seed_entity_ids.add(eid)

        # Fetch only the entities we need (single query by IDs)
        if seed_entity_ids:
            all_relevant_entities = self.db.query_in(KnowledgeEntity, "id", list(seed_entity_ids))
        else:
            all_relevant_entities = []
        entity_by_id = {ent.id: ent for ent in all_relevant_entities}

        # Build frontier from seed claims' entities
        frontier_entities: set[str] = set()
        for claim_id in seed_claim_ids:
            claim = claim_by_id[claim_id]
            frontier_entities.update(eid for eid in (claim.entity_ids or []) if eid in entity_by_id)

        seen_entities = set(frontier_entities)
        gathered_claim_ids: set[str] = set(seed_claim_ids)

        # Per-hop expansion, bounded by max_kg_claims * 10
        max_gathered = max_kg_claims * 10
        frontier = set(frontier_entities)

        for _ in range(max(graph_hops, 0)):
            if not frontier:
                break
            # Gather claims whose entity_ids intersect the frontier
            # (bounded: only claims not yet gathered)
            new_claim_ids: set[str] = set()
            frontier_entity_list = list(frontier)
            if frontier_entity_list:
                # Use a set membership test rather than scanning all claims
                frontier_set = frontier
                for claim in seed_claims:
                    if claim.id in gathered_claim_ids:
                        continue
                    claim_eids = claim.entity_ids or []
                    if any(eid in frontier_set for eid in claim_eids):
                        new_claim_ids.add(claim.id)

            if not new_claim_ids:
                break

            gathered_claim_ids.update(new_claim_ids)
            if len(gathered_claim_ids) >= max_gathered:
                break

            # Fetch newly referenced entities
            new_entity_ids: set[str] = set()
            for cid in new_claim_ids:
                claim = claim_by_id.get(cid)
                if claim is None:
                    continue
                for eid in (claim.entity_ids or []):
                    if eid not in entity_by_id and eid not in seen_entities:
                        new_entity_ids.add(eid)

            if new_entity_ids:
                new_ents = self.db.query_in(KnowledgeEntity, "id", list(new_entity_ids))
                for ent in new_ents:
                    entity_by_id[ent.id] = ent

            # Expand frontier
            next_frontier: set[str] = set()
            for cid in new_claim_ids:
                claim = claim_by_id.get(cid)
                if claim is None:
                    continue
                for eid in (claim.entity_ids or []):
                    if eid in entity_by_id and eid not in seen_entities:
                        seen_entities.add(eid)
                        next_frontier.add(eid)
            frontier = next_frontier

        # Final: fetch any claims from gathered IDs not yet in claim_by_id
        # (from hop expansion) and sort
        missing_claim_ids = gathered_claim_ids - set(claim_by_id.keys())
        if missing_claim_ids:
            extra_claims = self.db.query_in(KnowledgeClaim, "id", list(missing_claim_ids))
            for c in extra_claims:
                claim_by_id[c.id] = c

        ordered_claims = sorted(
            (claim_by_id[cid] for cid in gathered_claim_ids if cid in claim_by_id),
            key=lambda c: (
                0 if c.source_document_id in seed_doc_ids else 1,
                c.id,
            ),
        )[:max_kg_claims]

        for claim in ordered_claims:
            entity_names = [
                entity_by_id[eid].canonical_name
                for eid in (claim.entity_ids or [])
                if eid in entity_by_id
            ]
            source_text = content_by_doc_id.get(claim.source_document_id, "")
            content = (
                f"Claim: {claim.text}\n"
                f"Entities: {', '.join(entity_names) if entity_names else 'None'}\n"
                f"SVO: {claim.subject_canonical or ''} | {claim.predicate_verb or ''} | {claim.object_phrase or ''}\n"
                f"Source excerpt: {claim.source_excerpt or self._excerpt(source_text, max_chars=280)}"
            )
            payload.context_docs.append(
                {
                    "id": f"kg-claim:{claim.id}",
                    "name": f"KG claim {claim.id}",
                    "content": content,
                    "kind": "kg_claim",
                }
            )

        payload.kg_claims_used = len(ordered_claims)
        payload.kg_entities_used = len(seen_entities)

    def _read_content(self, doc: Document) -> str | None:
        if doc.page_content:
            return doc.page_content
        if self._file_reader is None:
            return None
        return self._file_reader(doc.path)

    @staticmethod
    def _excerpt(text: str | None, max_chars: int = 200) -> str:
        if not text:
            return ""
        return text[:max_chars] + "..." if len(text) > max_chars else text
