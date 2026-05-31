from fichero.knowledge_models import KnowledgeClaim, KnowledgeEntity
from fichero.models import Document
from fichero.retrieval.graph_rag import GraphAwareRetriever


class TestGraphAwareRetriever:
    def test_retrieve_returns_vector_docs_when_no_kg(self, db):
        doc = Document(
            id="doc-1",
            name="Archive note",
            page_content="Ada Lovelace wrote notes on the Analytical Engine.",
        )
        db.save(doc)
        db.embed(doc)

        retriever = GraphAwareRetriever(db)
        payload = retriever.retrieve(
            query="Who wrote notes on the Analytical Engine?",
            max_sources=3,
        )

        assert len(payload.context_docs) == 1
        assert payload.context_docs[0]["id"] == "doc-1"
        assert payload.context_docs[0]["kind"] == "document"
        assert payload.kg_claims_used == 0
        assert payload.kg_entities_used == 0

    def test_retrieve_augments_with_kg_neighborhood_claims(self, db):
        doc_1 = Document(
            id="doc-a",
            name="Town report",
            page_content="Ada served as mayor in Popayan.",
        )
        doc_2 = Document(
            id="doc-b",
            name="Council minutes",
            page_content="The council in Popayan documented municipal works.",
        )
        db.save(doc_1)
        db.save(doc_2)
        db.embed(doc_1)
        db.embed(doc_2)

        db.save(KnowledgeEntity(id="ent-ada", canonical_name="Ada Lovelace"))
        db.save(KnowledgeEntity(id="ent-popayan", canonical_name="Popayan"))
        db.save(KnowledgeEntity(id="ent-council", canonical_name="Town Council"))

        db.save(
            KnowledgeClaim(
                id="claim-1",
                text="Ada served as mayor in Popayan.",
                source_document_id="doc-a",
                entity_ids=["ent-ada", "ent-popayan"],
                predicate_verb="served as",
                object_phrase="mayor in Popayan",
            )
        )
        db.save(
            KnowledgeClaim(
                id="claim-2",
                text="Town Council ran municipal works in Popayan.",
                source_document_id="doc-b",
                entity_ids=["ent-council", "ent-popayan"],
                predicate_verb="ran",
                object_phrase="municipal works in Popayan",
            )
        )

        retriever = GraphAwareRetriever(db)
        payload = retriever.retrieve(
            query="Who governed Popayan?",
            max_sources=2,
            graph_hops=1,
            max_kg_claims=4,
        )

        kinds = [item["kind"] for item in payload.context_docs]
        assert "document" in kinds
        assert "kg_claim" in kinds
        assert payload.kg_claims_used >= 2
        assert payload.kg_entities_used >= 2

        claim_ids = {
            item["id"] for item in payload.context_docs if item["kind"] == "kg_claim"
        }
        assert "kg-claim:claim-1" in claim_ids
        assert "kg-claim:claim-2" in claim_ids

    def test_retrieve_skips_kg_when_graph_hops_zero(self, db):
        doc = Document(
            id="doc-z",
            name="Single doc",
            page_content="Ada served as mayor in Popayan.",
        )
        db.save(doc)
        db.embed(doc)
        db.save(KnowledgeEntity(id="ent-ada", canonical_name="Ada Lovelace"))
        db.save(
            KnowledgeClaim(
                id="claim-z",
                text="Ada served as mayor in Popayan.",
                source_document_id="doc-z",
                entity_ids=["ent-ada"],
            )
        )

        payload = GraphAwareRetriever(db).retrieve(
            query="Who served?",
            max_sources=3,
            graph_hops=0,
            max_kg_claims=12,
        )

        kinds = [item["kind"] for item in payload.context_docs]
        assert "document" in kinds
        assert "kg_claim" in kinds  # seed-claim context still allowed

    def test_retrieve_respects_max_kg_claims_zero(self, db):
        doc = Document(
            id="doc-k0",
            name="No kg limit",
            page_content="Ada served as mayor in Popayan.",
        )
        db.save(doc)
        db.embed(doc)
        db.save(KnowledgeEntity(id="ent-k0", canonical_name="Ada Lovelace"))
        db.save(
            KnowledgeClaim(
                id="claim-k0",
                text="Ada served as mayor in Popayan.",
                source_document_id="doc-k0",
                entity_ids=["ent-k0"],
            )
        )

        payload = GraphAwareRetriever(db).retrieve(
            query="Who served?",
            max_sources=3,
            graph_hops=1,
            max_kg_claims=0,
        )

        kinds = [item["kind"] for item in payload.context_docs]
        assert kinds == ["document"]
        assert payload.kg_claims_used == 0
