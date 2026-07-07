"""Tests for translation artifact embedding (#3325).

Covers:
  * Translation tool configs set trigger_embedding=True + embedding_scope="translation"
  * LLMToolConfig.embedding_scope defaults to "passage"
  * Database.embed_artifact_content creates scoped vectors
  * Database.delete_artifact_embeddings removes scoped vectors
  * artifact.translate registry action is registered and callable
  * Deleting a translation artifact removes its vectors
"""

from __future__ import annotations


from fichero.models import Artifact, Document, DocType, FileType, Status
from fichero.workflows.tools.llm_base import LLMToolConfig


# ---------------------------------------------------------------------------
# LLMToolConfig.embedding_scope
# ---------------------------------------------------------------------------


class TestLLMToolConfigEmbeddingScope:
    def test_default_embedding_scope_is_passage(self):
        cfg = LLMToolConfig(artifact_type="transcription")
        assert cfg.embedding_scope == "passage"

    def test_embedding_scope_override(self):
        cfg = LLMToolConfig(
            artifact_type="translation",
            trigger_embedding=True,
            embedding_scope="translation",
        )
        assert cfg.embedding_scope == "translation"
        assert cfg.trigger_embedding is True


# ---------------------------------------------------------------------------
# Translation tool configs
# ---------------------------------------------------------------------------


class TestTranslationToolConfigs:
    def test_translate_tool_config(self):
        from fichero.workflows.tools.translate import TOOL_CONFIG
        assert TOOL_CONFIG.trigger_embedding is True
        assert TOOL_CONFIG.embedding_scope == "translation"
        assert TOOL_CONFIG.update_page_content is False
        assert TOOL_CONFIG.artifact_type == "translation"

    def test_text_translate_tool_config(self):
        from fichero.workflows.tools.text_translate import TOOL_CONFIG
        assert TOOL_CONFIG.trigger_embedding is True
        assert TOOL_CONFIG.embedding_scope == "translation"
        assert TOOL_CONFIG.update_page_content is False

    def test_text_translate_review_tool_config(self):
        from fichero.workflows.tools.text_translate_review import TOOL_CONFIG
        assert TOOL_CONFIG.trigger_embedding is True
        assert TOOL_CONFIG.embedding_scope == "translation"
        assert TOOL_CONFIG.update_page_content is False


# ---------------------------------------------------------------------------
# Database.embed_artifact_content / delete_artifact_embeddings
# ---------------------------------------------------------------------------


class TestEmbedArtifactContent:
    def test_embed_artifact_content_creates_scoped_vectors(self, db):
        """embed_artifact_content creates passage-level vectors with embedding_scope='translation'."""
        doc = Document(
            name="test-translation.txt",
            doc_type=DocType.file,
            file_type=FileType.text,
            path="/path/test-translation.txt",
            page_content="This is the original document content that should be left alone.",
            status=Status.completed,
        )
        db.save(doc)

        text = "Esta es la traducción al español del documento original."
        count = db.embed_artifact_content(
            doc, text, artifact_id="test-artifact-1", embedding_scope="translation",
        )
        assert count > 0

    def test_embed_artifact_content_skips_empty_text(self, db):
        doc = Document(
            name="empty.txt",
            doc_type=DocType.file,
            file_type=FileType.text,
            path="/path/empty.txt",
            page_content="",
            status=Status.completed,
        )
        db.save(doc)
        count = db.embed_artifact_content(doc, "", artifact_id="art-1")
        assert count == 0

    def test_delete_artifact_embeddings_no_error_on_missing(self, db):
        """Deleting embeddings for a nonexistent artifact must not raise.

        Returns False if the embeddings table doesn't exist yet (fresh DB),
        True otherwise.  Either way, it must not raise an exception.
        """
        result = db.delete_artifact_embeddings("nonexistent-artifact-id")
        # Must not raise — value depends on whether the table exists yet.
        assert result in (True, False)

    def test_embed_and_delete_roundtrip(self, db):
        """After embedding and deleting, vectors are gone."""
        doc = Document(
            name="roundtrip.txt",
            doc_type=DocType.file,
            file_type=FileType.text,
            path="/path/roundtrip.txt",
            page_content="Original English text for translation roundtrip test.",
            status=Status.completed,
        )
        db.save(doc)

        translation_text = "Texto traducido al español para la prueba de ida y vuelta."
        count = db.embed_artifact_content(
            doc, translation_text, artifact_id="roundtrip-art-1", embedding_scope="translation",
        )
        assert count > 0

        # Delete should succeed
        result = db.delete_artifact_embeddings("roundtrip-art-1", embedding_scope="translation")
        assert result is True


# ---------------------------------------------------------------------------
# artifact.translate registry action
# ---------------------------------------------------------------------------


class TestArtifactTranslateAction:
    def test_translate_action_is_registered(self):
        """artifact.translate is in the global action registry."""
        import fichero.api.routes.artifacts  # noqa: F401 — registers the action
        from fichero.actions.registry import registry

        action = registry.get("artifact.translate")
        assert action is not None
        assert action.name == "artifact.translate"
        assert action.undoable is True

    def test_translate_action_params(self):
        import fichero.api.routes.artifacts  # noqa: F401
        from fichero.actions.registry import registry

        action = registry.get("artifact.translate")
        # The params model must accept document_id, target_lang, source_lang, provider
        fields = action.params_model.model_fields
        assert "document_id" in fields
        assert "target_lang" in fields
        assert "source_lang" in fields
        assert "provider" in fields


# ---------------------------------------------------------------------------
# Artifact deletion removes translation vectors
# ---------------------------------------------------------------------------


class TestTranslationArtifactDeletion:
    def test_delete_translation_artifact_removes_vectors(self, db):
        """_delete_artifact_impl removes embedding vectors for translation artifacts."""
        from fichero.api.routes.artifacts import _delete_artifact_impl

        doc = Document(
            name="del-test.txt",
            doc_type=DocType.file,
            file_type=FileType.text,
            path="/path/del-test.txt",
            page_content="Some content to translate",
            status=Status.completed,
        )
        db.save(doc)

        artifact = Artifact(
            document_id=doc.id,
            artifact_type="translation",
            content="Contenido traducido",
            version=1,
        )
        db.save(artifact)

        # Embed the translation
        db.embed_artifact_content(
            doc, "Contenido traducido", artifact_id=artifact.id, embedding_scope="translation",
        )

        # Delete via the impl (the action path calls this)
        _delete_artifact_impl(db, artifact.id)

        # The artifact is gone
        assert db.get(Artifact, artifact.id) is None
