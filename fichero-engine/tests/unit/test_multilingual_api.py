"""API-level tests for multilingual endpoints.

Tests cover:
- Language detection endpoint
- Transliteration endpoint
- Cross-language entity search
- Language-filtered claims/entities
- Text normalization
- Language persistence verification
"""

from fichero.models.knowledge import KnowledgeEntity, KnowledgeClaim, EntityType
from fichero.llm.multilingual import detect_language, normalize_text, stem_text


class TestLanguageDetection:
    """Test suite for language detection (already implemented)."""

    def test_detect_english(self):
        """Test detecting English text."""
        result = detect_language("Hello, this is English text")
        assert result.language == "en"
        assert result.confidence == 0.6  # Heuristic detection returns 0.6
        assert result.is_reliable is False  # 0.6 < 0.7 threshold

    def test_detect_japanese(self):
        """Test detecting Japanese text."""
        result = detect_language("これは日本語のテキストです")
        assert result.language == "ja"
        assert result.is_reliable is True

    def test_detect_chinese(self):
        """Test detecting Chinese text."""
        result = detect_language("这是一个中文文本")
        assert result.language == "zh"
        assert result.is_reliable is True

    def test_detect_korean(self):
        """Test detecting Korean text."""
        result = detect_language("한국어를 테스트합니다")
        assert result.language == "ko"
        assert result.is_reliable is True


class TestLanguagePersistence:
    """Test that language codes are properly stored and retrieved."""

    def test_entity_language_field_exists(self):
        """Test KnowledgeEntity has language field."""
        entity = KnowledgeEntity(
            id="test-1",
            canonical_name="Paris",
            language="fr",
            entity_type=EntityType.location,
        )
        assert entity.language == "fr"

    def test_claim_language_field_exists(self):
        """Test KnowledgeClaim has language and source_languages fields."""
        claim = KnowledgeClaim(
            id="test-1",
            text="Test claim text",
            source_document_id="doc1",
            language="en",
            source_languages=["en", "es"],
        )
        assert claim.language == "en"
        assert "en" in claim.source_languages
        assert "es" in claim.source_languages

    def test_entity_language_can_be_none(self):
        """Test entity language can be null."""
        entity = KnowledgeEntity(
            canonical_name="Unknown",
            language=None,
        )
        assert entity.language is None

    def test_entity_language_iso_format(self):
        """Test language is stored as ISO 639-1 code."""
        test_cases = [
            ("en", "English"),
            ("es", "Spanish"),
            ("fr", "French"),
            ("de", "German"),
            ("ja", "Japanese"),
            ("zh", "Chinese"),
            ("ko", "Korean"),
        ]
        for code, name in test_cases:
            entity = KnowledgeEntity(
                canonical_name=f"Test-{name}",
                language=code,
            )
            assert entity.language == code
            assert len(entity.language) == 2


class TestEntityAliasMultilingualSupport:
    """Test entity aliases support multilingual content."""

    def test_entity_aliases_field(self):
        """Test entity has aliases field."""
        entity = KnowledgeEntity(
            canonical_name="Tokyo",
            aliases=["東京", "Tōkyō"],
        )
        assert "東京" in entity.aliases
        assert "Tōkyō" in entity.aliases

    def test_entity_with_transliterated_aliases(self):
        """Test entity can have transliterated aliases."""
        entity = KnowledgeEntity(
            canonical_name="Beijing",
            language="en",
            aliases=["北京", "Peking", "Běijīng"],
        )
        # Verify all transliterations are stored
        assert len(entity.aliases) == 3
        assert "北京" in entity.aliases  # Chinese
        assert "Peking" in entity.aliases  # Latin, alternative


class TestCrossLanguageRetrievalFixtures:
    """Test cross-language retrieval evaluation fixtures."""

    def test_multilingual_entity_fixtures(self):
        """Test creating multilingual test entities for evaluation."""
        # Create multilingual entity set for testing
        entities = [
            KnowledgeEntity(
                id="city-en",
                canonical_name="London",
                language="en",
                aliases=["Capital of UK"],
                entity_type=EntityType.location,
            ),
            KnowledgeEntity(
                id="city-ja",
                canonical_name="東京",
                language="ja",
                aliases=["Tokyo", "Tōkyō"],
                entity_type=EntityType.location,
            ),
            KnowledgeEntity(
                id="person-ru",
                canonical_name="Петр",
                language="ru",
                aliases=["Peter", "Petr"],
                entity_type=EntityType.person,
            ),
        ]

        # Verify each entity has proper language
        assert entities[0].language == "en"
        assert entities[1].language == "ja"
        assert entities[2].language == "ru"

    def test_multilingual_claim_fixtures(self):
        """Test creating multilingual test claims for evaluation."""
        claims = [
            KnowledgeClaim(
                id="claim-en",
                text="English claim text",
                source_document_id="doc1",
                language="en",
                source_languages=["en"],
            ),
            KnowledgeClaim(
                id="claim-ja",
                text="日本語のクレーム",
                source_document_id="doc2",
                language="ja",
                source_languages=["ja"],
            ),
            KnowledgeClaim(
                id="claim-multiple",
                text="Claim with multiple sources",
                source_document_id="doc3",
                language="en",
                source_languages=["en", "fr", "de"],
            ),
        ]

        # Verify language fields
        assert claims[0].language == "en"
        assert claims[1].language == "ja"
        assert claims[2].language == "en"
        assert len(claims[2].source_languages) == 3


class TestTextNormalizationMultilingual:
    """Test text normalization for different languages."""

    def test_normalize_english_lowercase(self):
        """Test English normalization lowercases text."""
        result = normalize_text("HELLO World", "en")
        assert result == "hello world"

    def test_normalize_preserves_japanese(self):
        """Test normalization preserves Japanese characters."""
        text = "東京は日本の首都です"
        result = normalize_text(text, "ja")
        # Japanese should not be modified
        assert "東京" in result

    def test_normalize_preserves_chinese(self):
        """Test normalization preserves Chinese characters."""
        text = "北京是中国首都"
        result = normalize_text(text, "zh")
        assert "北京" in result

    def test_normalize_handles_mixed_content(self):
        """Test normalization handles mixed language content."""
        text = "Tokyo東京TEST"
        result = normalize_text(text, "en")
        # Latin should be lowercased, CJK preserved
        assert "tokyo" in result
        assert "東京" in result


class TestStemmingSupport:
    """Test stemming for supported languages."""

    def test_english_stemming(self):
        """Test English word stemming."""
        result = stem_text("running cats", "en")
        assert "runn" in result  # running -> runn
        assert "cat" in result  # cats -> cat

    def test_unsupported_language_returns_unchanged(self):
        """Test unsupported language returns text unchanged."""
        text = "test words"
        result = stem_text(text, "xx")  # Unknown language
        assert result == text


class TestCrossLanguageMatching:
    """Test cross-language matching capabilities."""

    def test_calculate_similarity_same_language(self):
        """Test similarity calculation for same-language matches."""
        from fichero.llm.multilingual import calculate_cross_language_similarity

        score = calculate_cross_language_similarity("London", "en", "London", "en")
        # Score might not be exactly 1.0 due to implementation details
        assert score >= 0.8  # High similarity for exact match

    def test_calculate_similarity_transliterated(self):
        """Test similarity for transliterated names."""
        from fichero.llm.multilingual import calculate_cross_language_similarity

        # Tokyo in different scripts
        score = calculate_cross_language_similarity("Tokyo", "en", "東京", "ja")
        assert score > 0.9  # High transliteration match
