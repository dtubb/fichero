"""`Database.embed()` must say WHY it did not embed (#4395).

Measured on Daniel's real libraries: the Local library has 668 documents with
text and 0 of them embedded, while Marshall sits at 449/452. Nothing anywhere
reported the difference — not the import, not the activity record, not the
logs. The reason nothing reported it is this method's return type.

``embed()`` returns a bare ``False`` for four materially different outcomes
(``db/__init__.py:3937-3976``):

1. no embeddable text — a legitimate skip;
2. content below ``MIN_CONTENT_LENGTH``, or marker-only ('[sin texto]') —
   a legitimate skip, logged at ``debug``;
3. ``save_passage_embeddings`` returned 0 — **no log at all**;
4. an exception, e.g. the embedding model cannot be loaded — an
   infrastructure failure, logged at ``warning``.

Cases 1 and 2 mean "this document has nothing worth embedding" and are
correct. Case 4 means "search is silently degrading for every document in
this run" and is an outage. Collapsing them into one falsy value makes it
impossible for any caller to tell a healthy import from a broken one — and
every caller discards the value anyway (``ingest.py:392``,
``ingest.py:640``), because there is nothing useful to do with a bare bool.

These tests are written against the contract that SHOULD hold: the outcome
must carry its reason, and an infrastructure failure must be distinguishable
from a skip without reading the log. They FAIL today; that is the finding.
The fix belongs in product code this lane does not touch.

No test here skips. Everything runs against a temp library and a stubbed
embedder, so an absent model is not an excuse (#4365).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from fichero_server.db import Database
from fichero_server.models import Document


class EmbeddingModelUnavailable(RuntimeError):
    """Stand-in for the real infrastructure failure: model missing/unloadable."""


@pytest.fixture
def temp_db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.duckdb")
    yield db
    db.close()
    shutil.rmtree(tmpdir, ignore_errors=True)


def _doc(db, *, text: str | None, name: str = "page.pdf") -> Document:
    doc = Document(name=name, page_content=text)
    db.save(doc)
    return doc


def _outcome(db, doc):
    """Whatever embed() reports — today a bare bool, tomorrow richer."""
    return db.embed(doc)


class TestSkipIsDistinguishableFromFailure:
    def test_no_text_and_model_unavailable_do_not_report_the_same_outcome(
        self, temp_db, monkeypatch: pytest.MonkeyPatch
    ):
        """The core contract: a legitimate skip must not look like an outage.

        KNOWN FAILING — both return bare ``False``.

        A document with no text is fine and expected; an unloadable embedding
        model means every document in the run is silently losing its
        searchability. A caller that cannot tell these apart cannot report
        the second one, which is exactly why a library reached 668 documents
        with 0 embeddings without anyone noticing.
        """
        empty_doc = _doc(temp_db, text=None, name="blank.pdf")
        skip_outcome = _outcome(temp_db, empty_doc)

        def explode(*args, **kwargs):
            raise EmbeddingModelUnavailable("embedding model could not be loaded")

        monkeypatch.setattr(Database, "save_passage_embeddings", explode)
        monkeypatch.setattr(Database, "_embed_text", explode)

        good_doc = _doc(temp_db, text="Regression Person signed the deed in 1842." * 4)
        failure_outcome = _outcome(temp_db, good_doc)

        assert skip_outcome != failure_outcome, (
            "embed() reported the same outcome "
            f"({skip_outcome!r}) for a document with NO TEXT (a correct skip) "
            "and for an UNLOADABLE MODEL (an infrastructure failure). No "
            "caller can distinguish a healthy import from a broken one."
        )

    def test_model_unavailable_is_not_silently_falsy(
        self, temp_db, monkeypatch: pytest.MonkeyPatch
    ):
        """Infrastructure failure must be loud — raise, or report a reason.

        KNOWN FAILING — the exception is caught and turned into ``False``.

        Project rule: fail loudly, never fall back silently. A model that
        cannot be loaded is not a per-document condition to be logged and
        shrugged off; it is the same for every document that follows, so the
        first occurrence is the one worth surfacing.
        """

        def explode(*args, **kwargs):
            raise EmbeddingModelUnavailable("embedding model could not be loaded")

        monkeypatch.setattr(Database, "save_passage_embeddings", explode)
        monkeypatch.setattr(Database, "_embed_text", explode)
        doc = _doc(temp_db, text="Regression Person signed the deed in 1842." * 4)

        raised: Exception | None = None
        try:
            outcome = _outcome(temp_db, doc)
        except Exception as exc:
            raised = exc
            outcome = None

        if raised is not None:
            return  # loud enough: the failure propagated

        assert outcome is not False, (
            "embed() swallowed an unloadable-model failure and returned a bare "
            "False, identical to 'this document had nothing to embed'. It must "
            "either propagate or return an outcome that names the cause."
        )

    def test_zero_vectors_written_is_not_silent(
        self, temp_db, monkeypatch: pytest.MonkeyPatch
    ):
        """The wholly unlogged case: the writer reports 0 and embed() gives up.

        KNOWN FAILING — ``if count == 0: return False`` with no log line at
        all, so this outcome leaves no trace anywhere. A document with real
        text that produced no vectors is a malfunction, not a skip.
        """
        monkeypatch.setattr(
            Database, "save_passage_embeddings", lambda *a, **k: 0
        )
        doc = _doc(temp_db, text="Regression Person signed the deed in 1842." * 4)

        outcome = _outcome(temp_db, doc)
        empty_doc = _doc(temp_db, text=None, name="blank2.pdf")
        skip_outcome = _outcome(temp_db, empty_doc)

        assert outcome != skip_outcome, (
            "a document with real text that produced ZERO vectors reported the "
            f"same outcome ({outcome!r}) as a document with no text at all — "
            "and unlike every other branch this one logs nothing whatsoever"
        )


class TestSuccessStillWorks:
    """Guard the guard: the tests above must fail for the right reason.

    If embed() were broken outright, the contract tests would 'pass' by
    accident in some rewrites. Pin the happy path so a genuine success is
    still distinguishable from every failure mode above.
    """

    def test_a_document_with_text_embeds_successfully(
        self, temp_db, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(
            Database, "save_passage_embeddings", lambda *a, **k: 3
        )
        doc = _doc(temp_db, text="Regression Person signed the deed in 1842." * 4)

        assert _outcome(temp_db, doc) is not False, (
            "a document with ample text and a working writer must not report "
            "the same falsy outcome as a failure"
        )
