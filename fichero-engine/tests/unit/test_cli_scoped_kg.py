"""Tests for the scoped KG exploration CLI client methods (#1125 MVP).

The new methods on FicheroClient compose existing endpoints to answer
"entities at scope X" and "claims at scope X mentioning entity Y"
without new backend routes. Tests stub the HTTP layer with FakeClient
so they verify the orchestration logic — which endpoints are called,
how results are aggregated and filtered — independent of an actual
backend run.
"""

from __future__ import annotations

from typing import Any

from fichero.models.knowledge import (
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)
from fichero.models import DocType, Document


class FakeClient:
    """In-memory stand-in for FicheroClient with just enough surface
    area to exercise the scoped helpers. The real
    `entities_at_doc` / `entities_at_folder` / `claims_at_*` are
    plain Python methods on the real client; bind them onto this
    fake by name so the tests run the actual implementation.
    """

    def __init__(self) -> None:
        self.docs: dict[str, Document] = {}
        self.claims_by_doc: dict[str, list[KnowledgeClaim]] = {}
        self.entities: dict[str, KnowledgeEntity] = {}

    # -- methods that the real helpers call into ------------------
    def list_claims(
        self, *,
        source_document_id: str | None = None,
        entity_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        **_: Any,
    ) -> list[KnowledgeClaim]:
        rows = self.claims_by_doc.get(source_document_id or "", [])
        if entity_id:
            rows = [c for c in rows if entity_id in (c.entity_ids or [])]
        return rows[offset : offset + limit]

    def list_documents(
        self, *, parent_id: str | None = None, limit: int = 50,
        offset: int = 0, **_: Any,
    ) -> list[Document]:
        rows = [d for d in self.docs.values() if d.parent_id == parent_id]
        return rows[offset : offset + limit]

    def get_document(self, doc_id: str) -> Document:
        return self.docs[doc_id]

    def get_entity(self, entity_id: str) -> KnowledgeEntity:
        return self.entities[entity_id]

    def entity_documents(self, entity_id: str) -> list[Any]:
        # Build (document_id, claim_count) one-row stand-ins from the
        # claim store. The real EntityDocumentLink shape carries more
        # fields but the helper only reads document_id + claim_count.
        from types import SimpleNamespace

        per_doc: dict[str, int] = {}
        for doc_id, claims in self.claims_by_doc.items():
            n = sum(
                1 for c in claims
                if entity_id in (c.entity_ids or [])
            )
            if n > 0:
                per_doc[doc_id] = n
        return [
            SimpleNamespace(document_id=did, claim_count=n)
            for did, n in per_doc.items()
        ]


def _attach_helpers(fake: FakeClient) -> None:
    """Bind the real scoped-KG helper methods onto FakeClient so the
    test exercises the actual implementation, not a re-write."""
    from fichero.cli.client import FicheroClient

    for name in (
        "entities_at_doc",
        "entities_at_folder",
        "claims_at_doc",
        "claims_at_folder",
        "entity_context",
        "_collect_descendant_doc_ids",
    ):
        method = getattr(FicheroClient, name)
        # Bind unbound function to the instance so `self` resolves
        # to FakeClient.
        setattr(fake, name, method.__get__(fake, FakeClient))


def _make_doc(
    doc_id: str, *, doc_type: DocType = DocType.file,
    parent_id: str | None = None, name: str = "",
) -> Document:
    return Document(
        id=doc_id, parent_id=parent_id, doc_type=doc_type,
        name=name or doc_id,
    )


def _make_claim(claim_id: str, *, doc: str, entity_ids: list[str]) -> KnowledgeClaim:
    return KnowledgeClaim(
        id=claim_id, text=f"claim {claim_id}",
        source_document_id=doc, entity_ids=entity_ids,
    )


def _make_entity(entity_id: str, *, name: str, etype: EntityType) -> KnowledgeEntity:
    return KnowledgeEntity(
        id=entity_id, canonical_name=name, entity_type=etype,
    )


# ============================================================================
# entities_at_doc / entities_at_folder
# ============================================================================


class TestEntitiesAtScope:
    def test_at_doc_collects_from_direct_claims(self):
        fake = FakeClient()
        _attach_helpers(fake)
        # One doc, two claims, two entities.
        fake.docs["d1"] = _make_doc("d1")
        fake.entities["e1"] = _make_entity("e1", name="Pedro", etype=EntityType.person)
        fake.entities["e2"] = _make_entity("e2", name="Chocó", etype=EntityType.location)
        fake.claims_by_doc["d1"] = [
            _make_claim("c1", doc="d1", entity_ids=["e1"]),
            _make_claim("c2", doc="d1", entity_ids=["e2"]),
        ]
        ents = fake.entities_at_doc("d1")
        names = sorted(e.canonical_name for e in ents)
        assert names == ["Chocó", "Pedro"]

    def test_at_doc_walks_page_children(self):
        # PDF with 2 pages; claims live on each page.
        fake = FakeClient()
        _attach_helpers(fake)
        fake.docs["pdf"] = _make_doc("pdf", doc_type=DocType.file)
        fake.docs["pdf-p1"] = _make_doc(
            "pdf-p1", doc_type=DocType.page, parent_id="pdf",
        )
        fake.docs["pdf-p2"] = _make_doc(
            "pdf-p2", doc_type=DocType.page, parent_id="pdf",
        )
        fake.entities["e1"] = _make_entity(
            "e1", name="Maria", etype=EntityType.person,
        )
        fake.entities["e2"] = _make_entity(
            "e2", name="San Juan", etype=EntityType.location,
        )
        fake.claims_by_doc["pdf-p1"] = [
            _make_claim("c1", doc="pdf-p1", entity_ids=["e1"]),
        ]
        fake.claims_by_doc["pdf-p2"] = [
            _make_claim("c2", doc="pdf-p2", entity_ids=["e2"]),
        ]
        # Calling at-doc on the PDF should union across both pages.
        ents = fake.entities_at_doc("pdf")
        assert sorted(e.canonical_name for e in ents) == ["Maria", "San Juan"]

    def test_at_doc_filters_by_entity_type(self):
        fake = FakeClient()
        _attach_helpers(fake)
        fake.docs["d1"] = _make_doc("d1")
        fake.entities["e1"] = _make_entity(
            "e1", name="Pedro", etype=EntityType.person,
        )
        fake.entities["e2"] = _make_entity(
            "e2", name="Chocó", etype=EntityType.location,
        )
        fake.claims_by_doc["d1"] = [
            _make_claim("c1", doc="d1", entity_ids=["e1", "e2"]),
        ]
        ents = fake.entities_at_doc("d1", entity_type="location")
        assert [e.canonical_name for e in ents] == ["Chocó"]

    def test_at_folder_recursive_walk(self):
        fake = FakeClient()
        _attach_helpers(fake)
        # Folder > sub-folder > doc; claims on the leaf doc only.
        fake.docs["root"] = _make_doc("root", doc_type=DocType.folder)
        fake.docs["sub"] = _make_doc(
            "sub", doc_type=DocType.folder, parent_id="root",
        )
        fake.docs["leaf"] = _make_doc(
            "leaf", doc_type=DocType.file, parent_id="sub",
        )
        fake.entities["e1"] = _make_entity(
            "e1", name="Atrato", etype=EntityType.location,
        )
        fake.claims_by_doc["leaf"] = [
            _make_claim("c1", doc="leaf", entity_ids=["e1"]),
        ]
        ents = fake.entities_at_folder("root")
        assert [e.canonical_name for e in ents] == ["Atrato"]

    def test_at_folder_non_recursive(self):
        fake = FakeClient()
        _attach_helpers(fake)
        # When --non-recursive is set, sub-folder docs are ignored.
        fake.docs["root"] = _make_doc("root", doc_type=DocType.folder)
        fake.docs["sub"] = _make_doc(
            "sub", doc_type=DocType.folder, parent_id="root",
        )
        fake.docs["direct"] = _make_doc(
            "direct", doc_type=DocType.file, parent_id="root",
        )
        fake.docs["nested"] = _make_doc(
            "nested", doc_type=DocType.file, parent_id="sub",
        )
        fake.entities["e1"] = _make_entity(
            "e1", name="Direct", etype=EntityType.location,
        )
        fake.entities["e2"] = _make_entity(
            "e2", name="Nested", etype=EntityType.location,
        )
        fake.claims_by_doc["direct"] = [
            _make_claim("c1", doc="direct", entity_ids=["e1"]),
        ]
        fake.claims_by_doc["nested"] = [
            _make_claim("c2", doc="nested", entity_ids=["e2"]),
        ]
        # Recursive: both.
        all_ents = sorted(
            e.canonical_name for e in fake.entities_at_folder("root")
        )
        assert all_ents == ["Direct", "Nested"]
        # Non-recursive: just the direct child.
        # The helper walks descendants — when recursive=False we only
        # take direct children. The 'sub' folder is a direct child but
        # has no claims; 'direct' is also a direct child with a claim.
        direct_only = [
            e.canonical_name
            for e in fake.entities_at_folder("root", recursive=False)
        ]
        assert direct_only == ["Direct"]


# ============================================================================
# claims_at_doc / claims_at_folder
# ============================================================================


class TestClaimsAtScope:
    def test_at_doc_with_entity_filter(self):
        fake = FakeClient()
        _attach_helpers(fake)
        fake.docs["d1"] = _make_doc("d1")
        fake.claims_by_doc["d1"] = [
            _make_claim("c1", doc="d1", entity_ids=["e1"]),
            _make_claim("c2", doc="d1", entity_ids=["e2"]),
        ]
        # Filter to entity e2.
        result = fake.claims_at_doc("d1", entity_id="e2")
        assert [c.id for c in result] == ["c2"]

    def test_at_folder_walks_descendants(self):
        fake = FakeClient()
        _attach_helpers(fake)
        fake.docs["root"] = _make_doc("root", doc_type=DocType.folder)
        fake.docs["sub"] = _make_doc(
            "sub", doc_type=DocType.folder, parent_id="root",
        )
        fake.docs["leaf"] = _make_doc(
            "leaf", doc_type=DocType.file, parent_id="sub",
        )
        fake.claims_by_doc["leaf"] = [
            _make_claim("c1", doc="leaf", entity_ids=["e1"]),
            _make_claim("c2", doc="leaf", entity_ids=["e2"]),
        ]
        result = fake.claims_at_folder("root")
        assert [c.id for c in result] == ["c1", "c2"]


# ============================================================================
# entity_context
# ============================================================================


class TestEntityContext:
    def test_counts_by_scope(self):
        fake = FakeClient()
        _attach_helpers(fake)
        # Setup: 1 folder, 1 doc with 2 pages, claims on each page.
        fake.docs["folder"] = _make_doc("folder", doc_type=DocType.folder)
        fake.docs["doc"] = _make_doc(
            "doc", doc_type=DocType.file, parent_id="folder",
        )
        fake.docs["p1"] = _make_doc(
            "p1", doc_type=DocType.page, parent_id="doc",
        )
        fake.docs["p2"] = _make_doc(
            "p2", doc_type=DocType.page, parent_id="doc",
        )
        fake.claims_by_doc["p1"] = [
            _make_claim("c1", doc="p1", entity_ids=["e1"]),
        ]
        fake.claims_by_doc["p2"] = [
            _make_claim("c2", doc="p2", entity_ids=["e1"]),
        ]
        ctx = fake.entity_context("e1")
        assert ctx["entity_id"] == "e1"
        assert ctx["page_count"] == 2
        assert ctx["doc_count"] == 1
        assert ctx["folder_count"] == 1
        assert ctx["claim_count"] == 2

    def test_empty_when_no_mentions(self):
        fake = FakeClient()
        _attach_helpers(fake)
        ctx = fake.entity_context("ghost")
        assert ctx["page_count"] == 0
        assert ctx["doc_count"] == 0
        assert ctx["claim_count"] == 0
