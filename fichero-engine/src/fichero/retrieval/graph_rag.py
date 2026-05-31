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
                min_score=0.0,
                search_type="hybrid",
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
        all_claims = self.db.query(KnowledgeClaim)
        all_entities = self.db.query(KnowledgeEntity)
        if not all_claims or not all_entities:
            return

        entity_by_id = {ent.id: ent for ent in all_entities}
        claim_by_id = {claim.id: claim for claim in all_claims}

        seed_claim_ids = {
            claim.id
            for claim in all_claims
            if claim.source_document_id in seed_doc_ids
            or any(sid in seed_doc_ids for sid in (claim.source_ids or []))
        }
        frontier_entities: set[str] = set()
        for claim_id in seed_claim_ids:
            claim = claim_by_id[claim_id]
            frontier_entities.update(eid for eid in (claim.entity_ids or []) if eid in entity_by_id)

        seen_entities = set(frontier_entities)
        gathered_claim_ids = set(seed_claim_ids)
        frontier = set(frontier_entities)

        for _ in range(max(graph_hops, 0)):
            if not frontier:
                break
            next_frontier: set[str] = set()
            for claim in all_claims:
                claim_entity_ids = [eid for eid in (claim.entity_ids or []) if eid in entity_by_id]
                if not claim_entity_ids:
                    continue
                if not any(eid in frontier for eid in claim_entity_ids):
                    continue
                gathered_claim_ids.add(claim.id)
                for eid in claim_entity_ids:
                    if eid not in seen_entities:
                        seen_entities.add(eid)
                        next_frontier.add(eid)
            frontier = next_frontier

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

