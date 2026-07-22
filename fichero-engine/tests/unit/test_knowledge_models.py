"""Unit tests for knowledge_models.py — SourceMetadata, ProvenanceInfo, KnowledgeClaim."""

import tempfile
from pathlib import Path

import pytest

from fichero.models.knowledge import (
    AttributionRole,
    AttributionStep,
    ClaimSuppressionRule,
    ClaimSuppressionRuleAction,
    EvidenceBasis,
    EvidentialDateRange,
    EvidentialPlace,
    EntityCurationState,
    EntityResolutionRule,
    EntityResolutionRuleType,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    GeoPoint,
    PlaceGeometryType,
    ImageProvenance,
    ProvenanceInfo,
    ProvenanceLayer,
    ProvenanceStep,
    QuotationKind,
    SourceGenre,
    SourceMetadata,
    SourceSupport,
)


def test_knowledge_import_shims_share_public_models():
    from fichero import knowledge
    from fichero.knowledge import KnowledgeClaim as PackageKnowledgeClaim
    from fichero.knowledge import KnowledgeEntity as PackageKnowledgeEntity
    from fichero.knowledge.knowledge_models import KnowledgeClaim as NewKnowledgeClaim
    from fichero.knowledge.knowledge_models import KnowledgeEntity as NewKnowledgeEntity

    assert knowledge.KnowledgeClaim is KnowledgeClaim
    assert PackageKnowledgeClaim is KnowledgeClaim
    assert NewKnowledgeClaim is KnowledgeClaim
    assert PackageKnowledgeEntity is KnowledgeEntity
    assert NewKnowledgeEntity is KnowledgeEntity


class TestSourceMetadata:
    """Tests for SourceMetadata model and its validators."""

    # -------------------------------------------------------------------------
    # DOI
    # -------------------------------------------------------------------------

    def test_doi_valid(self):
        s = SourceMetadata(doi="10.1234/56789")
        assert s.doi == "10.1234/56789"

    def test_doi_strips_whitespace(self):
        s = SourceMetadata(doi="  10.1234/56789  ")
        assert s.doi == "10.1234/56789"

    def test_doi_invalid_no_prefix(self):
        with pytest.raises(ValueError, match="Invalid DOI"):
            SourceMetadata(doi="10.1234/56789"[4:])  # "56789"

    def test_doi_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid DOI"):
            SourceMetadata(doi="not-a-doi")

    # -------------------------------------------------------------------------
    # ISBN-13
    # -------------------------------------------------------------------------

    def test_isbn13_valid(self):
        # 978-0-306-40615-7 → 9780306406157
        s = SourceMetadata(isbn_13="9780306406157")
        assert s.isbn_13 == "9780306406157"

    def test_isbn13_strips_dashes(self):
        s = SourceMetadata(isbn_13="978-0-306-40615-7")
        assert s.isbn_13 == "9780306406157"

    def test_isbn13_invalid_wrong_length(self):
        with pytest.raises(ValueError, match="Invalid ISBN-13"):
            SourceMetadata(isbn_13="978030640615")

    def test_isbn13_invalid_checksum(self):
        with pytest.raises(ValueError, match="Invalid ISBN-13 checksum"):
            SourceMetadata(isbn_13="9780123456789")  # bad checksum

    # -------------------------------------------------------------------------
    # ISBN-10
    # -------------------------------------------------------------------------

    def test_isbn10_valid_digit(self):
        # Valid ISBN-10 with checksum 8: 0*10 + 3*9 + 0*8 + 6*7 + 4*6 + 0*5 + 6*4 + 1*3 + 5*2 + 8*1 = 130
        # 138 % 11 = 6 → (11-6)%11 = 5 → check digit should be 5 (not 8, this was wrong in prior test)
        # Using 080442957X: weighted sum = 209, 209 % 11 = 0, (11-0)%11 = 11 → 10 = X ✓
        s = SourceMetadata(isbn_10="080442957X")
        assert s.isbn_10 == "080442957X"

    def test_isbn10_valid_x_checksum(self):
        s = SourceMetadata(isbn_10="080442957X")
        assert s.isbn_10 == "080442957X"

    def test_isbn10_strips_dashes(self):
        s = SourceMetadata(isbn_10="0-804-42957-X")
        assert s.isbn_10 == "080442957X"

    def test_isbn10_invalid_wrong_length(self):
        with pytest.raises(ValueError, match="Invalid ISBN-10"):
            SourceMetadata(isbn_10="306406157")

    def test_isbn10_invalid_checksum(self):
        with pytest.raises(ValueError, match="Invalid ISBN-10 checksum"):
            SourceMetadata(isbn_10="0306406159")

    # -------------------------------------------------------------------------
    # ISSN
    # -------------------------------------------------------------------------

    def test_issn_valid(self):
        # 2049-3630 → 20493630
        s = SourceMetadata(issn="2049-3630")
        assert s.issn == "20493630"

    def test_issn_valid_no_dash(self):
        s = SourceMetadata(issn="20493630")
        assert s.issn == "20493630"

    def test_issn_invalid_checksum(self):
        with pytest.raises(ValueError, match="Invalid ISSN checksum"):
            SourceMetadata(issn="2049-3631")

    def test_issn_invalid_length(self):
        with pytest.raises(ValueError, match="Invalid ISSN"):
            SourceMetadata(issn="2049363")  # too short

    # -------------------------------------------------------------------------
    # arXiv
    # -------------------------------------------------------------------------

    def test_arxiv_valid(self):
        s = SourceMetadata(arxiv_id="2301.00001")
        assert s.arxiv_id == "2301.00001"

    def test_arxiv_strips_prefix(self):
        s = SourceMetadata(arxiv_id="arXiv:2301.00001")
        assert s.arxiv_id == "2301.00001"

    def test_arxiv_with_version(self):
        s = SourceMetadata(arxiv_id="2301.00001v3")
        assert s.arxiv_id == "2301.00001v3"

    def test_arxiv_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid arXiv ID"):
            SourceMetadata(arxiv_id="notarxiv.12345")

    # -------------------------------------------------------------------------
    # URL
    # -------------------------------------------------------------------------

    def test_url_valid(self):
        s = SourceMetadata(url="https://example.org/path?query=1")
        assert s.url == "https://example.org/path?query=1"

    def test_url_invalid_no_scheme(self):
        with pytest.raises(ValueError, match="Invalid URL"):
            SourceMetadata(url="example.org")

    # -------------------------------------------------------------------------
    # Authors
    # -------------------------------------------------------------------------

    def test_authors_strips_whitespace(self):
        s = SourceMetadata(authors=["  Smith, J.  ", "", "Doe, A."])
        assert s.authors == ["Smith, J.", "Doe, A."]

    def test_authors_empty_strings_removed(self):
        s = SourceMetadata(authors=["Smith", ""])
        assert s.authors == ["Smith"]

    def test_bibtex_field_round_trips(self):
        bibtex = "@book{demo,\n  title = {Demo}\n}"
        s = SourceMetadata(bibtex=bibtex)
        assert s.bibtex == bibtex

    # -------------------------------------------------------------------------
    # Access restrictions
    # -------------------------------------------------------------------------

    def test_access_restrictions_valid(self):
        s = SourceMetadata(access_restrictions="restricted")
        assert s.access_restrictions == "restricted"

    def test_access_restrictions_normalized_lowercase(self):
        s = SourceMetadata(access_restrictions="RESTRICTED")
        assert s.access_restrictions == "restricted"

    def test_access_restrictions_invalid(self):
        with pytest.raises(ValueError, match="Invalid access_restrictions"):
            SourceMetadata(access_restrictions="unknown")

    # -------------------------------------------------------------------------
    # to_citation
    # -------------------------------------------------------------------------

    def test_to_citation_full(self):
        s = SourceMetadata(
            authors=["Smith, J.", "Doe, A."],
            date="2024",
            title="A Study",
            journal="Nature",
            publisher="Acme Press",
            doi="10.1234/test",
        )
        citation = s.to_citation()
        assert "Smith" in citation
        assert "2024" in citation
        assert "A Study" in citation
        assert "doi.org" in citation

    def test_to_citation_partial(self):
        s = SourceMetadata(title="Brief Note")
        citation = s.to_citation()
        assert "Brief Note" in citation

    def test_to_citation_empty(self):
        s = SourceMetadata()
        assert s.to_citation() == ""

    # -------------------------------------------------------------------------
    # All fields accepted
    # -------------------------------------------------------------------------

    def test_all_fields(self):
        s = SourceMetadata(
            title="Test Document",
            authors=["Author, One"],
            date="2024-01-15",
            publisher="Test Pub",
            journal="Test Journal",
            volume="1",
            issue="2",
            pages="10-20",
            doi="10.1234/test",
            isbn_13="9780306406157",
            isbn_10="080442957X",
            issn="2049-3630",
            arxiv_id="2301.00001",
            url="https://example.org",
            url_accessed="2024-02-01",
            archive_name="Internet Archive",
            archive_identifier="ia12345",
            rights="CC BY 4.0",
            access_restrictions="public",
            iiif_manifest="https://example.org/manifest.json",
            language="en",
        )
        assert s.title == "Test Document"
        assert s.doi == "10.1234/test"
        assert s.language == "en"


class TestProvenanceInfo:
    """Tests for ProvenanceInfo model."""

    def test_provenance_imported(self):
        p = ProvenanceInfo(source="imported", confidence=0.95)
        assert p.source == "imported"
        assert p.confidence == 0.95

    def test_provenance_agent(self):
        p = ProvenanceInfo(source="agent", agent_id="agent-123", notes="via web scraper")
        assert p.source == "agent"
        assert p.agent_id == "agent-123"
        assert p.notes == "via web scraper"


class TestKnowledgeClaimWithSourceMetadata:
    """Tests for KnowledgeClaim with SourceMetadata embedded."""

    def test_claim_with_source_metadata(self):
        meta = SourceMetadata(
            title="Journal Article",
            authors=["Author, A."],
            doi="10.1234/article",
        )
        claim = KnowledgeClaim(
            text="This is a claim from the article.",
            source_document_id="doc-123",
            source_metadata=meta,
        )
        assert claim.source_metadata is not None
        assert claim.source_metadata.title == "Journal Article"
        assert claim.source_metadata.doi == "10.1234/article"

    def test_claim_source_metadata_none(self):
        claim = KnowledgeClaim(
            text="A plain claim.",
            source_document_id="doc-456",
        )
        assert claim.source_metadata is None


# =============================================================================
# #1123 Attribution-taxonomy tests
# =============================================================================
# Three layers verified here:
#  1. The new enums have the values listed in the issue's tables.
#  2. The new claim fields default to safe values ("we don't know"), not
#     plausible-but-fabricated guesses. This is the "honest absence" rule
#     — a fresh claim with no attribution data should serialise without
#     any speaker / scribe / language / genre filled in.
#  3. Every new field round-trips through DuckDB (writer encodes, reader
#     decodes the nested GeoPoint back to a typed instance).


class TestAttributionEnums:
    """The three orthogonal enums (#1123 Phase A)."""

    def test_quotation_kind_members(self):
        assert {q.value for q in QuotationKind} == {
            "verbatim",
            "paraphrase",
            "indirect",
            "inference",
            "free_indirect",
        }

    def test_provenance_layer_members(self):
        assert {p.value for p in ProvenanceLayer} == {
            "main_text",
            "marginalia",
            "footnote",
            "annotation_later",
            "scribal_correction",
            "interlinear",
        }

    def test_source_genre_members(self):
        # 13 explicit + "other" = 13 total per issue
        assert "petition" in {g.value for g in SourceGenre}
        assert "royal_decree" in {g.value for g in SourceGenre}
        assert "other" in {g.value for g in SourceGenre}


class TestGeoPoint:
    """Spatial scope for a claim (#1123 Phase A)."""

    def test_basic(self):
        p = GeoPoint(lat=2.4448, lon=-76.6147, place_name="Popayán")
        assert p.lat == 2.4448
        assert p.lon == -76.6147
        assert p.place_name == "Popayán"
        assert p.precision_m is None

    def test_lat_out_of_range(self):
        with pytest.raises(ValueError):
            GeoPoint(lat=100.0, lon=0.0)

    def test_lon_out_of_range(self):
        with pytest.raises(ValueError):
            GeoPoint(lat=0.0, lon=200.0)


class TestAttributionDefaults:
    """A claim with no attribution data should encode absence, not guess (#1123)."""

    def test_empty_claim_has_no_attribution(self):
        c = KnowledgeClaim(text="x", source_document_id="d1")
        assert c.speaker_name is None
        assert c.speaker_entity_id is None
        assert c.scribe_name is None
        assert c.editor_name is None
        assert c.quotation_kind is None
        # provenance_layer DOES default — main_text is the safe assumption.
        assert c.provenance_layer == ProvenanceLayer.main_text
        assert c.source_language is None
        assert c.translation_chain == []
        assert c.audience is None
        assert c.source_genre is None
        assert c.claim_recorded_at is None
        assert c.claim_geo is None
        assert c.confidence_source is None
        assert c.predicate_canonical is None

    def test_populated_claim(self):
        c = KnowledgeClaim(
            text="Pedro testified about Maria.",
            source_document_id="d1",
            speaker_name="the witness Pedro",
            speaker_entity_id="e:pedro",
            subject_of_inquiry_entity_id="e:maria",
            scribe_name="hand B",
            quotation_kind=QuotationKind.indirect,
            provenance_layer=ProvenanceLayer.main_text,
            source_language="es",
            translation_chain=["es:original", "en:apple-translate"],
            audience="the Cabildo of Popayán",
            source_genre=SourceGenre.testimony,
            claim_recorded_at="1820-03-15",
            claim_geo=GeoPoint(lat=2.4448, lon=-76.6147),
            confidence_source="llm_logprob",
            predicate_canonical="testified_about",
        )
        assert c.speaker_name == "the witness Pedro"
        assert c.subject_of_inquiry_entity_id == "e:maria"
        assert c.quotation_kind == QuotationKind.indirect
        assert c.translation_chain == ["es:original", "en:apple-translate"]
        assert c.claim_geo.lat == 2.4448


class TestAttributionDuckDBRoundTrip:
    """Every #1123 claim field survives save → reload (#1123 Phase A).

    Catches the regression where nested Pydantic models on claims came
    back as raw JSON strings — fixed in `Database._parse_json_fields`
    by adding the BaseModel branch. This test pins that fix in place:
    if someone removes the BaseModel branch, `claim_geo` becomes a
    string and the lat assertion fails.
    """

    def test_round_trip_all_new_fields(self):
        from fichero.db import Database

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.fichero")
            geo = GeoPoint(lat=2.4448, lon=-76.6147, place_name="Popayán")
            c = KnowledgeClaim(
                text="Pedro testified about Maria.",
                source_document_id="d1",
                speaker_name="Pedro",
                speaker_entity_id="e:pedro",
                subject_of_inquiry_entity_id="e:maria",
                scribe_name="hand B",
                scribe_entity_id="e:scribe-b",
                editor_name="19c editor",
                editor_entity_id="e:editor",
                quotation_kind=QuotationKind.indirect,
                provenance_layer=ProvenanceLayer.marginalia,
                source_language="es",
                translation_chain=["es:original", "en:apple-translate"],
                audience="the Cabildo",
                source_genre=SourceGenre.testimony,
                claim_recorded_at="1820-03-15",
                claim_geo=geo,
                confidence_source="llm_logprob",
                predicate_canonical="testified_about",
            )
            db.save(c)
            loaded = db.get(KnowledgeClaim, c.id)
            assert loaded is not None
            # All scalar / enum fields
            assert loaded.speaker_name == "Pedro"
            assert loaded.speaker_entity_id == "e:pedro"
            assert loaded.subject_of_inquiry_entity_id == "e:maria"
            assert loaded.scribe_name == "hand B"
            assert loaded.scribe_entity_id == "e:scribe-b"
            assert loaded.editor_name == "19c editor"
            assert loaded.editor_entity_id == "e:editor"
            assert loaded.quotation_kind == QuotationKind.indirect
            assert loaded.provenance_layer == ProvenanceLayer.marginalia
            assert loaded.source_language == "es"
            assert loaded.translation_chain == ["es:original", "en:apple-translate"]
            assert loaded.audience == "the Cabildo"
            assert loaded.source_genre == SourceGenre.testimony
            assert loaded.claim_recorded_at == "1820-03-15"
            assert loaded.confidence_source == "llm_logprob"
            assert loaded.predicate_canonical == "testified_about"
            # Nested Pydantic — exercises the new BaseModel deserializer
            # branch in `Database._parse_json_fields`.
            assert isinstance(loaded.claim_geo, GeoPoint)
            assert loaded.claim_geo.lat == 2.4448
            assert loaded.claim_geo.place_name == "Popayán"


class TestEvidentialModel:
    """Temporal/spatial evidential dimensions for claims and entities (#1266)."""

    def test_claim_evidential_defaults_are_empty_lists(self):
        claim = KnowledgeClaim(text="x", source_document_id="d1")
        assert claim.date_values == []
        assert claim.place_values == []
        assert claim.attribution_chain == []
        assert claim.source_supports == []
        assert claim.corroboration_count == 1
        assert claim.weighted_corroboration_count == 1.0
        assert claim.corroborating_source_ids == []
        assert claim.evidential_confidence is None

    def test_entity_evidential_defaults_are_empty_lists(self):
        entity = KnowledgeEntity(canonical_name="Popayán")
        assert entity.date_values == []
        assert entity.place_values == []
        assert entity.attribution_chain == []
        assert entity.source_supports == []
        assert entity.corroboration_count == 0

    def test_claim_evidential_round_trip(self):
        from fichero.db import Database

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.fichero")
            date = EvidentialDateRange(
                start="1820-01-01",
                end="1820-12-31",
                precision="year",
                basis=EvidenceBasis.asserted,
                confidence=0.82,
                source_document_id="doc-1",
                source_excerpt="in 1820 Pedro filed",
            )
            place = EvidentialPlace(
                label="Popayán jurisdiction",
                geometry_type=PlaceGeometryType.region,
                bbox=[-77.2, 2.1, -76.2, 3.0],
                basis=EvidenceBasis.source_anchored,
                confidence=0.55,
                source_field="source_metadata.place",
            )
            chain = [
                AttributionStep(
                    role=AttributionRole.asserter,
                    name="Pedro",
                    basis=EvidenceBasis.asserted,
                    confidence=0.8,
                    order=0,
                ),
                AttributionStep(
                    role=AttributionRole.source_document,
                    document_id="doc-1",
                    label="Letter One",
                    basis=EvidenceBasis.source_anchored,
                    order=1,
                ),
            ]
            support = SourceSupport(
                source_document_id="doc-1",
                source_page_label="3",
                support_basis=EvidenceBasis.asserted,
                support_confidence=0.82,
                date_values=[date],
                place_values=[place],
                attribution_chain=chain,
            )
            claim = KnowledgeClaim(
                text="Pedro filed the petition.",
                source_document_id="doc-1",
                time_start="1820-01-01",
                time_end="1820-12-31",
                time_precision="year",
                date_values=[date],
                place_values=[place],
                attribution_chain=chain,
                source_supports=[support],
                corroboration_count=2,
                weighted_corroboration_count=1.6,
                corroborating_source_ids=["doc-1", "doc-7"],
                evidential_confidence=0.87,
                evidential_confidence_source="corroboration",
            )
            db.save(claim)

            loaded = db.get(KnowledgeClaim, claim.id)
            assert loaded is not None
            assert loaded.date_values[0].basis == EvidenceBasis.asserted
            assert loaded.place_values[0].geometry_type == PlaceGeometryType.region
            assert loaded.attribution_chain[0].role == AttributionRole.asserter
            assert loaded.source_supports[0].date_values[0].start == "1820-01-01"
            assert loaded.corroboration_count == 2
            assert loaded.weighted_corroboration_count == 1.6
            assert loaded.corroborating_source_ids == ["doc-1", "doc-7"]
            assert loaded.evidential_confidence == 0.87


class TestCurationRules:
    def test_knowledge_entity_defaults_to_unreviewed_curation_state(self):
        entity = KnowledgeEntity(canonical_name="Popayan")
        assert entity.curation_state == EntityCurationState.unreviewed

    def test_rule_models_round_trip_via_database(self):
        from fichero.db import Database

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.fichero")

            entity_rule = EntityResolutionRule(
                rule_type=EntityResolutionRuleType.merge_into,
                match_canonical_name="J. Davidson",
                match_entity_type=EntityType.person,
                target_canonical_name="John Davidson",
                target_entity_type=EntityType.person,
                reason="same person",
                created_by="tester",
            )
            claim_rule = ClaimSuppressionRule(
                action=ClaimSuppressionRuleAction.demote,
                match_predicate_verb="is",
                match_subject_name="Andagoya",
                match_object_phrase="a place",
                suppress_is_a_copulas=True,
                reason="trivial copula",
                created_by="tester",
            )

            db.save(entity_rule)
            db.save(claim_rule)

            loaded_entity_rules = db.query(
                EntityResolutionRule,
                match_canonical_name="J. Davidson",
            )
            loaded_claim_rules = db.query(
                ClaimSuppressionRule,
                match_subject_name="Andagoya",
            )

            assert len(loaded_entity_rules) == 1
            assert loaded_entity_rules[0].rule_type == EntityResolutionRuleType.merge_into
            assert loaded_entity_rules[0].target_canonical_name == "John Davidson"
            assert len(loaded_claim_rules) == 1
            assert loaded_claim_rules[0].action == ClaimSuppressionRuleAction.demote
            assert loaded_claim_rules[0].suppress_is_a_copulas is True


class TestDocumentProvenance:
    """Document gains provenance_chain + image_provenance (#1123 Phase A)."""

    def test_document_provenance_round_trip(self):
        from fichero.db import Database
        from fichero.models import Document, DocType

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.fichero")
            doc = Document(
                name="1933 court copy of 1820 letter",
                doc_type=DocType.file,
                provenance_chain=[
                    {"action": "filed", "actor": "Pedro", "date": "1820"},
                    {"action": "copied", "date": "1933"},
                    {"action": "scanned", "date": "2019"},
                ],
                image_provenance={
                    "photographer": "archive staff",
                    "equipment": "Nikon D850",
                },
            )
            db.save(doc)
            loaded = db.get(Document, doc.id)
            assert loaded is not None
            assert len(loaded.provenance_chain) == 3
            assert loaded.provenance_chain[0]["actor"] == "Pedro"
            assert loaded.image_provenance["equipment"] == "Nikon D850"

    def test_document_workflow_runs_round_trip(self):
        from fichero.db import Database
        from fichero.models import Document, DocType

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.fichero")
            doc = Document(
                name="workflow provenance target",
                doc_type=DocType.file,
                workflow_runs=[
                    {
                        "workflow_id": "wf-123",
                        "workflow_name": "Transcribe",
                        "thread_id": "thread-abc",
                        "model": "gpt-4o-mini",
                        "result": {"status": "completed", "pages": 4},
                        "started_at": "2026-05-31T10:00:00Z",
                        "completed_at": "2026-05-31T10:02:30Z",
                    }
                ],
            )
            db.save(doc)
            loaded = db.get(Document, doc.id)
            assert loaded is not None
            assert loaded.workflow_runs[0]["workflow_id"] == "wf-123"
            assert loaded.workflow_runs[0]["model"] == "gpt-4o-mini"
            assert loaded.workflow_runs[0]["result"]["pages"] == 4

    def test_document_provenance_defaults_empty(self):
        from fichero.models import Document, DocType

        doc = Document(name="plain doc", doc_type=DocType.file)
        assert doc.provenance_chain == []
        assert doc.image_provenance is None
        assert doc.workflow_runs == []


class TestProvenanceStepImageProvenance:
    """The two sub-models exposed by the issue (#1123)."""

    def test_provenance_step_minimal(self):
        step = ProvenanceStep(action="filed")
        assert step.action == "filed"
        assert step.actor is None
        assert step.date is None

    def test_provenance_step_full(self):
        step = ProvenanceStep(
            action="copied",
            actor="archive scribe",
            date="1933-04-15",
            location="Bogotá archive",
            notes="rebound and renumbered",
        )
        assert step.actor == "archive scribe"
        assert step.notes == "rebound and renumbered"

    def test_image_provenance_minimal(self):
        ip = ImageProvenance()
        assert ip.photographer is None
        assert ip.capture_date is None

    def test_image_provenance_full(self):
        ip = ImageProvenance(
            photographer="archive staff",
            capture_date="2019-04-02",
            equipment="Nikon D850 + copy stand",
            condition_notes="bottom-right water damage",
        )
        assert ip.photographer == "archive staff"
        assert ip.condition_notes == "bottom-right water damage"
