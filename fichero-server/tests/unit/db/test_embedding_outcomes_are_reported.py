"""Embedding failures must not be swallowed (#4395).

Daniel asked "are we getting embeddings working properly yet?" — a question
the app should be able to answer itself. I measured his real library first:

    documents with text : 669
    document embeddings :  12

But the KG embedding tables held 54 entity and 149 claim vectors, so **the
model loads fine**. The cause was not #4304's download failure: it was
`_create_pdf_page_children(auto_embed=False)` on the two paths that create
page children outside the main import — the workflow source backfill and the
whole-PDF guard — which together produced 676 of his 745 documents.

Nothing said so, because `Database.embed` returned a bare `bool`, every caller
discarded it, and each failure was one `logger.warning` among thousands.

Three fixes, in the order that matters: the default alone would have fixed
today's symptom and left the next occurrence just as invisible.

Nothing here skips or needs a model.
"""

from __future__ import annotations


from fichero_server.db import EmbedOutcome


class TestTheOutcomeCarriesItsReason:
    """A bare bool could not distinguish a legitimate skip from a broken
    library — both were False, and both looked like nothing was wrong."""

    def test_a_document_with_no_text_is_a_skip_not_a_failure(self):
        outcome = EmbedOutcome(embedded=False, reason="no_embeddable_text")
        assert not outcome.is_infrastructure_failure, (
            "an unembeddable document must not be reported as a broken "
            "library, or the real signal drowns in legitimate skips"
        )

    def test_a_model_failure_is_infrastructure(self):
        outcome = EmbedOutcome(
            embedded=False, reason="embedding_failed", error="model not found"
        )
        assert outcome.is_infrastructure_failure, (
            "a failure that will repeat for every document is a broken "
            "library, not a per-document skip (#4395)"
        )
        assert outcome.error == "model not found"

    def test_success_carries_no_reason(self):
        assert EmbedOutcome(embedded=True, document_id="d1").embedded
        assert EmbedOutcome(embedded=True).reason is None


class TestEmbedRecordsWhyItDidNotEmbed:
    """The seam: `db.embed()` must leave behind why, not just whether."""

    @staticmethod
    def _db(tmp_path):
        from fichero_server.db import Database

        return Database(tmp_path / "embed.duckdb")

    def test_no_text_records_no_embeddable_text(self, tmp_path, monkeypatch):
        from fichero_server.models import Document

        db = self._db(tmp_path)
        try:
            monkeypatch.setattr(
                type(db), "_embedding_text_for_document", lambda *_a, **_k: ""
            )
            assert db.embed(Document(name="blank.txt")) is False
            assert db.last_embed_outcome.reason == "no_embeddable_text"
            assert not db.last_embed_outcome.is_infrastructure_failure
        finally:
            db.close()

    def test_a_raising_backend_records_an_infrastructure_failure(
        self, tmp_path, monkeypatch
    ):
        """The case that made a whole library silently unembedded."""
        from fichero_server.models import Document

        db = self._db(tmp_path)
        try:
            monkeypatch.setattr(
                type(db), "_embedding_text_for_document", lambda *_a, **_k: "text"
            )

            def _explode(*_a, **_k):
                raise RuntimeError("embedding model could not be loaded")

            monkeypatch.setattr(type(db), "save_passage_embeddings", _explode)

            assert db.embed(Document(name="page.txt")) is False
            outcome = db.last_embed_outcome
            assert outcome.reason == "embedding_failed"
            assert outcome.is_infrastructure_failure, (
                "a model that cannot load will fail for EVERY document — "
                "reporting it as a per-document skip is what let a library "
                "reach 669 documents and 12 embeddings silently"
            )
            assert "could not be loaded" in outcome.error
        finally:
            db.close()


class TestTheImportReportsCountsByReason:
    """One warning per document is thousands of unread lines. One line
    naming the causes is what answers 'are embeddings working?'."""

    @staticmethod
    def _summarise(counts, *, auto_embed=True, pages=10):
        from fichero_server.importers.ingest import _log_embed_summary

        return _log_embed_summary(
            counts, "marshall.pdf", pages, auto_embed=auto_embed
        )

    def test_zero_embedded_is_reported_as_an_error_not_a_warning(self, caplog):
        """The reported situation. An import that embedded NOTHING is broken,
        not partially successful, and must not read like the latter."""
        with caplog.at_level("INFO"):
            self._summarise({"embedded": 0, "embedding_failed": 12})

        errors = [r for r in caplog.records if r.levelname == "ERROR"]
        assert errors, "an import that embedded nothing was not escalated"
        assert "0 of 12" in errors[0].getMessage()
        assert "infrastructure failure" in errors[0].getMessage()

    def test_partial_failure_names_the_reasons(self, caplog):
        with caplog.at_level("INFO"):
            self._summarise({"embedded": 8, "embedding_failed": 2})

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warnings
        message = warnings[0].getMessage()
        assert "8/10" in message
        assert "embedding_failed=2" in message

    def test_full_success_is_reported_once(self, caplog):
        with caplog.at_level("INFO"):
            self._summarise({"embedded": 10})

        infos = [r for r in caplog.records if r.levelname == "INFO"]
        assert any("10/10" in r.getMessage() for r in infos)

    def test_a_skip_only_import_is_not_escalated(self, caplog):
        """Documents with no embeddable text are a legitimate outcome — they
        must not be reported as a broken library."""
        with caplog.at_level("INFO"):
            self._summarise({"embedded": 0, "no_embeddable_text": 5})

        errors = [r for r in caplog.records if r.levelname == "ERROR"]
        assert errors, "0 embedded is still worth surfacing"
        assert "no_embeddable_text=5" in errors[0].getMessage(), (
            "the reason must be named, or the user cannot tell a broken "
            "model from a folder of images"
        )

    def test_nothing_is_reported_when_embedding_was_not_requested(self, caplog):
        with caplog.at_level("INFO"):
            self._summarise({"embedded": 0}, auto_embed=False)
        assert [r for r in caplog.records if "EMBEDDINGS" in r.getMessage()] == []


class TestThePagePathsNowEmbed:
    """The cause. Both paths that create page children outside the main
    import passed `auto_embed=False`, and between them produced the bulk of
    a real library's documents."""

    def test_no_call_site_disables_embedding_any_more(self):
        """Parsed, not grepped.

        A substring check matches this rule's own explanatory comments, which
        would make it pass or fail for the wrong reason. The AST sees only
        real calls.
        """
        import ast
        import inspect

        from fichero_server.importers import ingest
        from fichero_server.workflows.tools import sources, vision_base

        offenders: list[str] = []
        for module in (sources, vision_base, ingest):
            tree = ast.parse(inspect.getsource(module))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "id", None) or getattr(
                    node.func, "attr", None
                )
                if name != "_create_pdf_page_children":
                    continue
                for keyword in node.keywords:
                    if keyword.arg == "auto_embed" and isinstance(
                        keyword.value, ast.Constant
                    ):
                        if keyword.value.value is False:
                            offenders.append(
                                f"{module.__name__}:{node.lineno}"
                            )

        assert offenders == [], (
            f"page children are created with embedding disabled at {offenders} "
            "— those documents can never be found by semantic search, which "
            "is how a real library reached 669 documents and 12 embeddings "
            "(#4395)"
        )
