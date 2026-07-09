from fichero.knowledge_models import KnowledgeClaim, KnowledgeEntity
from fichero.models import Document
from fichero.retrieval.graph_rag import GraphAwareRetriever, RetrievalPayload


class TestRetrievalPayload:
    def test_defaults_are_empty_and_instance_local(self):
        first = RetrievalPayload()
        second = RetrievalPayload()

        assert first.context_docs == []
        assert first.sources == []
        assert first.kg_claims_used == 0
        assert first.kg_entities_used == 0

        first.context_docs.append({"id": "doc-1"})
        first.sources.append({"document_id": "doc-1"})
        first.kg_claims_used = 1
        first.kg_entities_used = 2

        assert second.context_docs == []
        assert second.sources == []
        assert second.kg_claims_used == 0
        assert second.kg_entities_used == 0


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

    def test_retrieve_with_explicit_document_ids_skips_missing_and_contentless_docs(self, db):
        kept = Document(
            id="doc-kept",
            name="Kept",
            page_content="Ada Lovelace documented municipal work.",
        )
        empty = Document(id="doc-empty", name="Empty", page_content="")
        db.save(kept)
        db.save(empty)

        payload = GraphAwareRetriever(db).retrieve(
            query="ignored when document_ids supplied",
            max_sources=5,
            document_ids=["doc-missing", "doc-empty", "doc-kept"],
        )

        assert [item["id"] for item in payload.context_docs] == ["doc-kept"]
        assert [item["document_id"] for item in payload.sources] == ["doc-kept"]
        assert payload.kg_claims_used == 0
        assert payload.kg_entities_used == 0

    def test_retrieve_treats_source_ids_as_seed_claim_links(self, db):
        seed = Document(
            id="doc-seed",
            name="Seed doc",
            page_content="Leidy appears in the town record.",
        )
        witness = Document(
            id="doc-witness",
            name="Witness doc",
            page_content="Another record connects Leidy to Quibdo.",
        )
        db.save(seed)
        db.save(witness)
        db.embed(seed)
        db.embed(witness)

        db.save(KnowledgeEntity(id="ent-leidy", canonical_name="Leidy"))
        db.save(KnowledgeEntity(id="ent-quibdo", canonical_name="Quibdo"))
        db.save(
            KnowledgeClaim(
                id="claim-seed-via-source-ids",
                text="Leidy is mentioned in the source packet.",
                source_document_id="doc-elsewhere",
                source_ids=["doc-seed"],
                entity_ids=["ent-leidy"],
                source_excerpt="Seed excerpt",
            )
        )
        db.save(
            KnowledgeClaim(
                id="claim-hop",
                text="Leidy appears in Quibdo.",
                source_document_id="doc-witness",
                entity_ids=["ent-leidy", "ent-quibdo"],
                source_excerpt="Witness excerpt",
            )
        )

        payload = GraphAwareRetriever(db).retrieve(
            query="Where does Leidy appear?",
            max_sources=2,
            graph_hops=1,
            max_kg_claims=4,
        )

        claim_ids = [
            item["id"] for item in payload.context_docs if item["kind"] == "kg_claim"
        ]
        assert "kg-claim:claim-seed-via-source-ids" in claim_ids
        assert "kg-claim:claim-hop" in claim_ids
        assert payload.kg_claims_used == 2
        assert payload.kg_entities_used == 2

    def test_retrieve_expands_hop_claims_for_explicit_document_scope(self, db):
        seed = Document(
            id="doc-hop-seed",
            name="Seed doc",
            page_content="Ada served in Popayan.",
        )
        witness = Document(
            id="doc-hop-witness",
            name="Witness doc",
            page_content="Popayan later elected Bruno.",
        )
        db.save(seed)
        db.save(witness)

        db.save(KnowledgeEntity(id="ent-hop-ada", canonical_name="Ada"))
        db.save(KnowledgeEntity(id="ent-hop-popayan", canonical_name="Popayan"))
        db.save(KnowledgeEntity(id="ent-hop-bruno", canonical_name="Bruno"))
        db.save(
            KnowledgeClaim(
                id="claim-hop-seed",
                text="Ada served in Popayan.",
                source_document_id="doc-hop-seed",
                entity_ids=["ent-hop-ada", "ent-hop-popayan"],
            )
        )
        db.save(
            KnowledgeClaim(
                id="claim-hop-neighbor",
                text="Bruno was elected in Popayan.",
                source_document_id="doc-hop-witness",
                entity_ids=["ent-hop-bruno", "ent-hop-popayan"],
            )
        )

        payload = GraphAwareRetriever(db).retrieve(
            query="Who served in Popayan?",
            max_sources=1,
            document_ids=["doc-hop-seed"],
            graph_hops=1,
            max_kg_claims=4,
        )

        claim_ids = {
            item["id"] for item in payload.context_docs if item["kind"] == "kg_claim"
        }
        assert "kg-claim:claim-hop-seed" in claim_ids
        assert "kg-claim:claim-hop-neighbor" in claim_ids

    def test_retrieve_avoids_full_claim_scan_for_multi_document_seed(self, db, monkeypatch):
        first = Document(
            id="doc-multi-a",
            name="Seed A",
            page_content="Ada served in Popayan.",
        )
        second = Document(
            id="doc-multi-b",
            name="Seed B",
            page_content="Bruno was elected in Popayan.",
        )
        for doc in (first, second):
            db.save(doc)
        db.save(KnowledgeEntity(id="ent-multi-ada", canonical_name="Ada"))
        db.save(KnowledgeEntity(id="ent-multi-popayan", canonical_name="Popayan"))
        db.save(
            KnowledgeClaim(
                id="claim-multi-a",
                text="Ada served in Popayan.",
                source_document_id="doc-multi-a",
                entity_ids=["ent-multi-ada", "ent-multi-popayan"],
            )
        )

        original_query = db.query

        def guarded_query(model, **filters):
            if model is KnowledgeClaim and not filters:
                raise AssertionError("full claim scan")
            return original_query(model, **filters)

        monkeypatch.setattr(db, "query", guarded_query)

        payload = GraphAwareRetriever(db).retrieve(
            query="ignored",
            max_sources=2,
            document_ids=["doc-multi-a", "doc-multi-b"],
            graph_hops=1,
            max_kg_claims=4,
        )

        assert payload.kg_claims_used == 1

    def test_retrieve_prefers_seed_claims_before_hop_claims_when_truncated(self, db):
        doc_a = Document(
            id="doc-a2",
            name="Seed A",
            page_content="Ada met Bruno in Popayan.",
        )
        doc_b = Document(
            id="doc-b2",
            name="Seed B",
            page_content="Bruno worked with Carmen.",
        )
        doc_c = Document(
            id="doc-c2",
            name="Hop C",
            page_content="Carmen traveled onward.",
        )
        for doc in (doc_a, doc_b, doc_c):
            db.save(doc)
            db.embed(doc)

        db.save(KnowledgeEntity(id="ent-a2", canonical_name="Ada"))
        db.save(KnowledgeEntity(id="ent-b2", canonical_name="Bruno"))
        db.save(KnowledgeEntity(id="ent-c2", canonical_name="Carmen"))

        db.save(
            KnowledgeClaim(
                id="claim-a2",
                text="Ada met Bruno.",
                source_document_id="doc-a2",
                entity_ids=["ent-a2", "ent-b2"],
            )
        )
        db.save(
            KnowledgeClaim(
                id="claim-b2",
                text="Bruno worked with Carmen.",
                source_document_id="doc-b2",
                entity_ids=["ent-b2", "ent-c2"],
            )
        )
        db.save(
            KnowledgeClaim(
                id="claim-c2",
                text="Carmen traveled onward.",
                source_document_id="doc-c2",
                entity_ids=["ent-c2"],
            )
        )

        payload = GraphAwareRetriever(db).retrieve(
            query="What connects Ada and Bruno?",
            max_sources=2,
            graph_hops=2,
            max_kg_claims=2,
        )

        claim_ids = [
            item["id"] for item in payload.context_docs if item["kind"] == "kg_claim"
        ]
        assert claim_ids == ["kg-claim:claim-a2", "kg-claim:claim-b2"]
        assert "kg-claim:claim-c2" not in claim_ids
        assert payload.kg_claims_used == 2
