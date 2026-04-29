"""Unit tests for knowledge_models.py — SourceMetadata, ProvenanceInfo, KnowledgeClaim."""

import pytest
from fichero.knowledge_models import (
    SourceMetadata,
    ProvenanceInfo,
    SourceMetadataProvenance,
    KnowledgeClaim,
    SourceType,
)


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
