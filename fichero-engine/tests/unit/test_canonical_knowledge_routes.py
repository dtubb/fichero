"""Contract tests for canonical knowledge API routes.

Tests cover:
- Entities CRUD (POST, GET, PATCH, DELETE)
- Claims CRUD (POST, GET, PATCH, DELETE)
- Claim Links CRUD (POST, GET, PATCH, DELETE)
- Referential integrity validation
- Error handling
"""

from datetime import datetime

import pytest
from fastapi import HTTPException

from fichero.api.routes.entities import (
    EntityUpsertRequest,
    EntityAliasRequest,
    upsert_entity,
    list_entities,
    get_entity,
    add_entity_aliases,
)
from fichero.api.routes.claims import (
    ClaimCreateRequest,
    ClaimPatchRequest,
    create_claim,
    list_claims,
    get_claim,
    patch_claim,
)
from fichero.api.routes.claim_links import (
    ClaimLinkCreateRequest,
    ClaimLinkUpdateRequest,
    create_claim_link,
    list_claim_links,
    get_claim_link,
    update_claim_link,
    delete_claim_link,
)
from fichero.models.knowledge import (
    EntityType,
    ClaimType,
    ClaimCurationState,
    EpistemicStatus,
    SourceType,
    KnowledgeEntity,
    KnowledgeClaim,
    KnowledgeClaimLink,
    ClaimRelationType,
)
from fichero.models import Document


class TestEntitiesRoutes:
    """Test entity canonical API routes."""

    @pytest.mark.asyncio
    async def test_upsert_entity_creates_new(self, tmp_path):
        """POST /entities creates new entity."""
        from fichero.db import Database

        # NOTE: must NOT be ``tmp_path / "test.fichero"`` — the parent conftest's
        # ``test_package`` fixture (pulled in for every unit test via the autouse
        # ``_unit_test_auth_header`` → ``client`` chain) creates that exact path
        # as a package DIRECTORY, so a flat-file Database() on it would hit
        # "duckdb IOException: Is a directory".
        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        request = EntityUpsertRequest(
            canonical_name="Test Entity",
            entity_type=EntityType.person,
            language="en",
            aliases=["Alias1", "Alias2"],
        )

        entity = await upsert_entity(request, db)

        assert entity.canonical_name == "Test Entity"
        assert entity.entity_type == EntityType.person
        assert entity.language == "en"
        assert "Alias1" in entity.aliases

    @pytest.mark.asyncio
    async def test_upsert_entity_updates_existing(self, tmp_path):
        """POST /entities with ID updates existing entity."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        # Create initial entity
        create_req = EntityUpsertRequest(
            canonical_name="Original Name",
            entity_type=EntityType.person,
        )
        entity = await upsert_entity(create_req, db)
        entity_id = entity.id

        # Update entity
        update_req = EntityUpsertRequest(
            id=entity_id,
            canonical_name="Updated Name",
            entity_type=EntityType.organization,
        )
        updated = await upsert_entity(update_req, db)

        assert updated.id == entity_id
        assert updated.canonical_name == "Updated Name"
        assert updated.entity_type == EntityType.organization

    @pytest.mark.asyncio
    async def test_get_entity_by_id(self, tmp_path):
        """GET /entities/{id} returns entity."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        # Create entity
        request = EntityUpsertRequest(
            canonical_name="Test Entity",
            entity_type=EntityType.location,
        )
        entity = await upsert_entity(request, db)
        entity_id = entity.id

        # Get entity
        retrieved = await get_entity(entity_id, db)
        assert retrieved.id == entity_id
        assert retrieved.canonical_name == "Test Entity"

    @pytest.mark.asyncio
    async def test_get_entity_not_found(self, tmp_path):
        """GET /entities/{id} returns 404 for unknown ID."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        with pytest.raises(HTTPException) as exc:
            await get_entity("nonexistent-id", db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_add_aliases_to_entity(self, tmp_path):
        """POST /entities/{id}/aliases adds aliases."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        # Create entity
        request = EntityUpsertRequest(
            canonical_name="Test Entity",
            entity_type=EntityType.person,
            aliases=["Initial"],
        )
        entity = await upsert_entity(request, db)
        entity_id = entity.id

        # Add aliases
        alias_request = EntityAliasRequest(aliases=["New1", "New2"])
        updated = await add_entity_aliases(entity_id, alias_request, db)

        assert "Initial" in updated.aliases
        assert "New1" in updated.aliases
        assert "New2" in updated.aliases

    @pytest.mark.asyncio
    async def test_list_entities_with_filter(self, tmp_path):
        """GET /entities?q= filters by query."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        # Create entities
        await upsert_entity(
            EntityUpsertRequest(
                canonical_name="Alpha Entity",
                entity_type=EntityType.person,
            ),
            db,
        )
        await upsert_entity(
            EntityUpsertRequest(
                canonical_name="Beta Entity",
                entity_type=EntityType.person,
            ),
            db,
        )

        # List with filter
        results = await list_entities(q="Alpha", limit=50, db=db)
        assert len(results.items) == 1
        assert results.items[0].canonical_name == "Alpha Entity"


class TestClaimsRoutes:
    """Test claim canonical API routes."""

    @pytest.mark.asyncio
    async def test_create_claim_success(self, tmp_path):
        """POST /claims creates claim with valid data."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        # Create source document
        doc = Document(
            name="Test Source",
            path="/path/to/source.pdf",
            doc_type="file",
        )
        db.save(doc)

        # Create entity
        entity = await upsert_entity(
            EntityUpsertRequest(
                canonical_name="Test Entity",
                entity_type=EntityType.person,
            ),
            db,
        )

        request = ClaimCreateRequest(
            text="The sky is blue",
            source_document_id=doc.id,
            entity_ids=[entity.id],
            claim_type=ClaimType.fact,
            confidence=0.95,
        )

        claim = await create_claim(request, db)

        assert claim.text == "The sky is blue"
        assert claim.source_document_id == doc.id
        assert entity.id in claim.entity_ids
        assert claim.claim_type == ClaimType.fact
        assert claim.confidence == 0.95

    @pytest.mark.asyncio
    async def test_create_claim_missing_source(self, tmp_path):
        """POST /claims returns 404 for missing source."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        request = ClaimCreateRequest(
            text="Unsourced claim",
            source_document_id="nonexistent-doc",
        )

        with pytest.raises(HTTPException) as exc:
            await create_claim(request, db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_claim_missing_entity(self, tmp_path):
        """POST /claims returns 404 for missing entity."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        # Create source document
        doc = Document(
            name="Test Source",
            path="/path/to/source.pdf",
            doc_type="file",
        )
        db.save(doc)

        request = ClaimCreateRequest(
            text="Claim about nonexistent entity",
            source_document_id=doc.id,
            entity_ids=["nonexistent-entity"],
        )

        with pytest.raises(HTTPException) as exc:
            await create_claim(request, db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_claim_success(self, tmp_path):
        """PATCH /claims/{id} updates claim."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        # Create source and claim
        doc = Document(
            name="Test Source",
            path="/path/to/source.pdf",
            doc_type="file",
        )
        db.save(doc)

        request = ClaimCreateRequest(
            text="Original text",
            source_document_id=doc.id,
            confidence=0.5,
        )
        claim = await create_claim(request, db)

        # Update claim
        patch_request = ClaimPatchRequest(
            text="Updated text",
            confidence=0.9,
            curation_state=ClaimCurationState.curated,
        )
        updated = await patch_claim(claim.id, patch_request, db)

        assert updated.text == "Updated text"
        assert updated.confidence == 0.9
        assert updated.curation_state == ClaimCurationState.curated

    @pytest.mark.asyncio
    async def test_list_claims_filtered(self, tmp_path):
        """GET /claims filters by curation_state, claim_type, etc."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        # Create source
        doc = Document(
            name="Test Source",
            path="/path/to/source.pdf",
            doc_type="file",
        )
        db.save(doc)

        # Create claims with different types
        await create_claim(
            ClaimCreateRequest(
                text="Fact claim",
                source_document_id=doc.id,
                claim_type=ClaimType.fact,
                curation_state=ClaimCurationState.curated,
            ),
            db,
        )
        await create_claim(
            ClaimCreateRequest(
                text="Theory claim",
                source_document_id=doc.id,
                claim_type=ClaimType.theory,
                curation_state=ClaimCurationState.unreviewed,
            ),
            db,
        )

        # Filter by claim type
        results = await list_claims(claim_type=ClaimType.fact, limit=200, offset=0, db=db)
        assert len(results.items) == 1
        assert results.items[0].claim_type == ClaimType.fact

        # Filter by curation state
        curated = await list_claims(curation_state=ClaimCurationState.curated, limit=200, offset=0, db=db)
        assert len(curated.items) == 1
        assert curated.items[0].curation_state == ClaimCurationState.curated


class TestClaimLinksRoutes:
    """Test claim link canonical API routes."""

    @pytest.mark.asyncio
    async def test_create_claim_link_success(self, tmp_path):
        """POST /claims/{id}/links creates link between claims."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        # Create source and claims
        doc = Document(
            name="Test Source",
            path="/path/to/source.pdf",
            doc_type="file",
        )
        db.save(doc)

        claim1 = await create_claim(
            ClaimCreateRequest(
                text="First claim",
                source_document_id=doc.id,
            ),
            db,
        )
        claim2 = await create_claim(
            ClaimCreateRequest(
                text="Second claim",
                source_document_id=doc.id,
            ),
            db,
        )

        request = ClaimLinkCreateRequest(
            related_claim_id=claim2.id,
            relation_type=ClaimRelationType.supports,
            link_quality=0.8,
            evidence="Both claims agree",
        )

        link = await create_claim_link(claim1.id, request, db)

        assert link.claim_id == claim1.id
        assert link.related_claim_id == claim2.id
        assert link.relation_type == ClaimRelationType.supports
        assert link.link_quality == 0.8
        assert link.evidence == "Both claims agree"

    @pytest.mark.asyncio
    async def test_create_link_missing_claim(self, tmp_path):
        """POST /claims/{id}/links returns 404 for missing claim."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        request = ClaimLinkCreateRequest(
            related_claim_id="nonexistent",
            relation_type=ClaimRelationType.supports,
        )

        with pytest.raises(HTTPException) as exc:
            await create_claim_link("nonexistent-claim", request, db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_claim_links(self, tmp_path):
        """GET /claims/{id}/links returns all related links."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        # Create source and claims
        doc = Document(
            name="Test Source",
            path="/path/to/source.pdf",
            doc_type="file",
        )
        db.save(doc)

        claim1 = await create_claim(
            ClaimCreateRequest(
                text="First claim",
                source_document_id=doc.id,
            ),
            db,
        )
        claim2 = await create_claim(
            ClaimCreateRequest(
                text="Second claim",
                source_document_id=doc.id,
            ),
            db,
        )
        claim3 = await create_claim(
            ClaimCreateRequest(
                text="Third claim",
                source_document_id=doc.id,
            ),
            db,
        )

        # Create links
        await create_claim_link(
            claim1.id,
            ClaimLinkCreateRequest(
                related_claim_id=claim2.id,
                relation_type=ClaimRelationType.supports,
            ),
            db,
        )
        await create_claim_link(
            claim3.id,
            ClaimLinkCreateRequest(
                related_claim_id=claim1.id,
                relation_type=ClaimRelationType.contradicts,
            ),
            db,
        )

        links_response = await list_claim_links(claim1.id, db)
        assert len(links_response.items) == 2  # Both outgoing and incoming

    @pytest.mark.asyncio
    async def test_update_claim_link(self, tmp_path):
        """PATCH /claim-links/{id} updates link."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        # Create source and claims
        doc = Document(
            name="Test Source",
            path="/path/to/source.pdf",
            doc_type="file",
        )
        db.save(doc)

        claim1 = await create_claim(
            ClaimCreateRequest(
                text="First claim",
                source_document_id=doc.id,
            ),
            db,
        )
        claim2 = await create_claim(
            ClaimCreateRequest(
                text="Second claim",
                source_document_id=doc.id,
            ),
            db,
        )

        link = await create_claim_link(
            claim1.id,
            ClaimLinkCreateRequest(
                related_claim_id=claim2.id,
                relation_type=ClaimRelationType.supports,
                link_quality=0.5,
            ),
            db,
        )

        update = ClaimLinkUpdateRequest(
            link_quality=0.9,
            evidence="Stronger evidence found",
        )
        updated = await update_claim_link(link.id, update, db)

        assert updated.link_quality == 0.9
        assert updated.evidence == "Stronger evidence found"

    @pytest.mark.asyncio
    async def test_delete_claim_link(self, tmp_path):
        """DELETE /claim-links/{id} removes link."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        # Create source and claims
        doc = Document(
            name="Test Source",
            path="/path/to/source.pdf",
            doc_type="file",
        )
        db.save(doc)

        claim1 = await create_claim(
            ClaimCreateRequest(
                text="First claim",
                source_document_id=doc.id,
            ),
            db,
        )
        claim2 = await create_claim(
            ClaimCreateRequest(
                text="Second claim",
                source_document_id=doc.id,
            ),
            db,
        )

        link = await create_claim_link(
            claim1.id,
            ClaimLinkCreateRequest(
                related_claim_id=claim2.id,
                relation_type=ClaimRelationType.supports,
            ),
            db,
        )

        result = await delete_claim_link(link.id, db)
        assert result.success is True
        assert result.link_id == link.id


class TestReferentialIntegrity:
    """Test referential integrity across entities, claims, and links."""

    @pytest.mark.asyncio
    async def test_claim_references_valid_entities(self, tmp_path):
        """Claims can only reference existing entities."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        doc = Document(
            name="Test Source",
            path="/path/to/source.pdf",
            doc_type="file",
        )
        db.save(doc)

        # Should fail with invalid entity
        with pytest.raises(HTTPException) as exc:
            await create_claim(
                ClaimCreateRequest(
                    text="Claim with bad entity",
                    source_document_id=doc.id,
                    entity_ids=["invalid-id"],
                ),
                db,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_claim_link_references_valid_claims(self, tmp_path):
        """Claim links can only reference existing claims."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        # Should fail with invalid claim IDs
        with pytest.raises(HTTPException) as exc:
            await create_claim_link(
                "nonexistent",
                ClaimLinkCreateRequest(
                    related_claim_id="also-nonexistent",
                    relation_type=ClaimRelationType.supports,
                ),
                db,
            )
        assert exc.value.status_code == 404


class TestCanonicalAPIContract:
    """Verify canonical API contract - no business logic divergence."""

    @pytest.mark.asyncio
    async def test_entity_api_matches_model(self, tmp_path):
        """Entity API fields match KnowledgeEntity model."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        # Create entity via API
        request = EntityUpsertRequest(
            canonical_name="API Entity",
            entity_type=EntityType.person,
            language="en",
            aliases=["Alias1"],
            description="Test description",
            metadata={"key": "value"},
        )
        entity = await upsert_entity(request, db)

        # Verify all fields persisted correctly
        assert entity.canonical_name == "API Entity"
        assert entity.entity_type == EntityType.person
        assert entity.language == "en"
        assert "Alias1" in entity.aliases
        assert entity.description == "Test description"
        assert entity.metadata == {"key": "value"}

    @pytest.mark.asyncio
    async def test_claim_api_matches_model(self, tmp_path):
        """Claim API fields match KnowledgeClaim model."""
        from fichero.db import Database

        db_path = tmp_path / "kg.fichero"
        db = Database(str(db_path))

        doc = Document(
            name="Test Source",
            path="/path/to/source.pdf",
            doc_type="file",
        )
        db.save(doc)

        request = ClaimCreateRequest(
            text="API claim text",
            source_document_id=doc.id,
            source_type=SourceType.document,
            confidence=0.75,
            claim_type=ClaimType.fact,
            curation_state=ClaimCurationState.unreviewed,
            metadata={"source": "test"},
        )
        claim = await create_claim(request, db)

        # Verify all fields persisted
        assert claim.text == "API claim text"
        assert claim.source_document_id == doc.id
        assert claim.confidence == 0.75
        assert claim.claim_type == ClaimType.fact
        assert claim.metadata == {"source": "test"}
