"""Free NLP draft layer at import (#4823).

The ruling's architecture: cheap NLP proposes -> LLM/VLM normalizes -> user
curates. This file pins the parts that make the "draft" and "curation
persists" halves of that architecture actually true, using STUBBED
extractors (``ner_fn``/``svo_fn``/``filter_fn`` injection seams on
``run_nlp_draft``) so the orchestration is tested everywhere, independent of
whether a real spaCy model happens to be installed on the machine running
the suite. One test at the bottom exercises the REAL spaCy pipeline and
skips, visibly, when it is not available.
"""

from __future__ import annotations

import pytest

from fichero_server.importers import derivatives
from fichero_server.importers.nlp_draft import (
    AUTO_NLP_SETTING_KEY,
    NlpDraftResult,
    auto_nlp_enabled,
    needs_nlp,
    passes_draft_quality_gate,
    run_nlp_draft,
)
from fichero_server.knowledge.spacy_ner import readable_surface_form
from fichero_server.knowledge.spacy_ner import EntitySpan
from fichero_server.knowledge.spacy_svo import ProposedTriple
from fichero_server.models import Document, DocType, FileType, Status
from fichero_server.models.knowledge import (
    ClaimSuppressionRule,
    ClaimSuppressionRuleAction,
    EntityCurationState,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)


def _drain(futures, timeout: float = 30) -> None:
    """Wait for every future with a HARD per-future timeout that RAISES on
    a hang (team-lead review, 2026-09-18): the old `concurrent.futures.wait
    (futures, timeout=N)` does not raise when a future never completes --
    it just returns, and the test's own assertion then fails with an
    unhelpful diff while the underlying stuck WORKER THREAD keeps running
    forever, later hanging pytest's own process exit while it waits to
    join that thread (the exact background-suite hang this review traced
    to an unlocked concurrent spaCy pipeline call in `spacy_svo.py`).
    `future.result(timeout=...)` raises `TimeoutError` immediately and by
    name, turning a silent hang into a fast, diagnosable test failure.
    """
    for future in futures:
        future.result(timeout=timeout)


def _stub_ner(text, language=None):
    return [
        EntitySpan(text="Juan Perez", fichero_type="person", start=0, end=10, label="PERSON")
    ]


def _stub_svo(text, language=None):
    return [
        ProposedTriple(
            subject="Juan Perez",
            verb="firmó",
            object="la escritura",
            sentence=text,
            char_start=0,
            char_end=len(text),
        )
    ]


def _stub_filter(proposals, text):
    return proposals, []


def _stubs():
    return dict(ner_fn=_stub_ner, svo_fn=_stub_svo, filter_fn=_stub_filter)


def _text_doc(db, text="Juan Perez firmó la escritura.") -> Document:
    doc = Document(
        name="a.md", doc_type=DocType.file, file_type=FileType.text,
        status=Status.pending, page_content=text,
    )
    db.save(doc)
    return doc


# =============================================================================
# The orchestration: writes real entity + claim rows through the one writer.
# =============================================================================


class TestTheStageProducesADraft:
    def test_run_nlp_draft_writes_entity_and_claim_rows(self, db, test_package):
        doc = _text_doc(db)

        result = run_nlp_draft(db, doc, **_stubs())

        assert result.error is None
        assert result.entity_ids
        assert result.claim_ids
        entities = db.query(KnowledgeEntity, canonical_name="Juan Perez")
        assert len(entities) == 1
        assert entities[0].entity_type == EntityType.person

    def test_new_rows_are_unreviewed_drafts(self, db, test_package):
        """(R1) The draft marker IS the existing curation_state field --
        no new field, no migration."""
        doc = _text_doc(db)

        result = run_nlp_draft(db, doc, **_stubs())

        entity = db.get(KnowledgeEntity, result.entity_ids[0])
        assert entity.curation_state == EntityCurationState.unreviewed
        claim = db.get(KnowledgeClaim, result.claim_ids[0])
        from fichero_server.models.knowledge import ClaimCurationState

        assert claim.curation_state == ClaimCurationState.unreviewed

    def test_empty_page_is_not_an_error(self, db, test_package):
        doc = _text_doc(db, text="   ")

        result = run_nlp_draft(db, doc, **_stubs())

        assert result == NlpDraftResult()

    def test_extraction_failure_is_recorded_not_raised(self, db, test_package):
        def _boom(text, language=None):
            raise RuntimeError("parser exploded")

        doc = _text_doc(db)

        result = run_nlp_draft(db, doc, ner_fn=_boom, svo_fn=_stub_svo, filter_fn=_stub_filter)

        assert result.error is not None
        assert "parser exploded" in result.error


# =============================================================================
# S2: the draft-quality gate (team-lead review) -- pure function, tested
# with a table of good and bad names, then proven wired into the actual
# write path.
# =============================================================================


class TestDraftQualityGate:
    @pytest.mark.parametrize("name,fichero_type,expected", [
        # Good names must PASS, including accented Spanish and the dotted
        # paleographic form readable_surface_form exists to normalise.
        ("Juan Perez", "person", True),
        ("María José Gómez", "person", True),
        ("Chocó", "location", True),
        (readable_surface_form("Antonio.de.guzman"), "person", True),  # "Antonio de guzman"
        ("New York", "location", True),
        # OCR / structural noise must FAIL.
        ("12:10", "person", False),
        ("...", "person", False),
        ("--", "location", False),
        ("A", "person", False),  # too short
        ("Al", "person", False),  # 2 chars, but below the 3-char floor
        ("A1", "person", False),  # 1 letter, below the 2-letter floor
        ("1234567", "location", False),  # all-numeric
        ("I-95", "location", False),  # letter ratio < 0.5
        # All-caps headings / archival boilerplate a page's running head
        # might spuriously tag as an entity -- still real letters, still
        # passes the ratio gate. NOT rejected by this gate (a caps-only
        # heuristic was deliberately left out of v1 -- a real all-caps
        # surname is common in this corpus); documented here so a future
        # reviewer sees the decision was made, not missed.
        ("ARCHIVO GENERAL", "organization", True),
        # A single common function/stop word.
        ("el", "person", False),
        ("The", "concept", False),  # also excluded by type, belt+suspenders
        ("de", "location", False),
        # Excluded types (concept — ES MISC / EN WORK_OF_ART/LAW) always
        # fail regardless of how clean the name looks.
        ("Constitución de Cádiz", "concept", False),
    ])
    def test_the_gate_table(self, name, fichero_type, expected):
        assert passes_draft_quality_gate(name, fichero_type) is expected

    def test_a_garbage_span_never_reaches_the_writer(self, db, test_package):
        def _ner_with_garbage(text, language=None):
            return [
                EntitySpan(text="Juan Perez", fichero_type="person", start=0, end=10, label="PERSON"),
                EntitySpan(text="12:10", fichero_type="person", start=11, end=16, label="PERSON"),
                EntitySpan(text="el", fichero_type="person", start=17, end=19, label="PERSON"),
            ]

        doc = _text_doc(db)

        result = run_nlp_draft(
            db, doc, ner_fn=_ner_with_garbage, svo_fn=_stub_svo, filter_fn=_stub_filter
        )

        names = {e.canonical_name for e in db.query(KnowledgeEntity)}
        assert result is not None
        assert "Juan Perez" in names
        assert "12:10" not in names
        assert "el" not in names

    def test_concept_type_is_excluded_from_the_draft_layer_entirely(self, db, test_package):
        def _ner_concept_only(text, language=None):
            return [
                EntitySpan(text="Constitución de Cádiz", fichero_type="concept", start=0, end=10, label="WORK_OF_ART")
            ]

        doc = _text_doc(db)

        result = run_nlp_draft(
            db, doc, ner_fn=_ner_concept_only, svo_fn=lambda *a, **kw: [], filter_fn=lambda p, t: (p, [])
        )

        assert result.entity_ids == []
        assert db.query(KnowledgeEntity, entity_type=EntityType.concept) == []

    def test_per_document_cap_truncates_visibly(self, db, test_package, monkeypatch):
        from fichero_server.importers import nlp_draft as nlp_draft_module

        monkeypatch.setattr(nlp_draft_module, "_DRAFT_MAX_ENTITIES_PER_DOCUMENT", 2)

        def _many_entities(text, language=None):
            return [
                EntitySpan(text=f"Persona {i}", fichero_type="person", start=0, end=10, label="PERSON")
                for i in range(5)
            ]

        doc = _text_doc(db)

        result = run_nlp_draft(
            db, doc, ner_fn=_many_entities, svo_fn=lambda *a, **kw: [], filter_fn=lambda p, t: (p, [])
        )

        assert result.truncated is True
        assert len(result.entity_ids) == 2

    def test_truncation_is_recorded_on_the_document_visibly(
        self, db, test_package, monkeypatch
    ):
        from fichero_server.importers import nlp_draft as nlp_draft_module

        monkeypatch.setattr(nlp_draft_module, "_DRAFT_MAX_ENTITIES_PER_DOCUMENT", 1)
        monkeypatch.setattr(
            nlp_draft_module,
            "run_nlp_draft",
            lambda db_, doc_, **kw: NlpDraftResult(entity_ids=["e1"], claim_ids=[], truncated=True),
        )
        doc = _text_doc(db)

        derivatives._nlp_stage(doc.id, test_package)

        after = db.get(Document, doc.id)
        assert after.metadata.get("nlp_truncated") is True
        assert "nlp_processed_at" in after.metadata


# =============================================================================
# Missing model: a visible state, never a silent skip, never a wrong-language
# parse.
# =============================================================================


class TestMissingModelIsVisible:
    def test_model_not_installed_is_a_visible_error_not_a_silent_empty_result(
        self, db, test_package, monkeypatch
    ):
        from fichero_server.knowledge import spacy_ner

        monkeypatch.setattr(spacy_ner, "is_pipeline_available", lambda lang: False)
        doc = _text_doc(db)

        result = run_nlp_draft(db, doc, **_stubs())

        assert result.error is not None
        assert "not installed" in result.error
        assert result.entity_ids == []
        assert result.claim_ids == []

    def test_missing_model_for_the_resolved_language_never_falls_back_to_english(
        self, db, test_package, monkeypatch
    ):
        """Statement-language-matches-the-document ruling: a Spanish page
        with no Spanish model installed gets the visible not-installed
        state, NEVER an English parse standing in for it."""
        from fichero_server.knowledge import spacy_ner

        calls: list[str] = []
        real_available = spacy_ner.is_pipeline_available

        def _only_en_available(lang):
            calls.append(lang)
            return lang == "en"

        monkeypatch.setattr(spacy_ner, "is_pipeline_available", _only_en_available)
        doc = Document(
            name="es.md", doc_type=DocType.file, file_type=FileType.text,
            status=Status.pending, page_content="Juan Perez firmó la escritura.",
            language="es",
        )
        db.save(doc)

        def _fail_if_called(*a, **kw):
            raise AssertionError("must not run NER once the model is known missing")

        result = run_nlp_draft(
            db, doc, ner_fn=_fail_if_called, svo_fn=_fail_if_called, filter_fn=_fail_if_called
        )

        assert result.error is not None
        assert "es" in result.error
        assert "en" not in calls or "es" in calls  # resolved to es, not silently swapped
        assert real_available  # sanity: the real function still exists


class TestNoSilentLanguageFallback:
    """#4914 (normalization.ner.no-silent-language-fallback): a language with
    no spaCy model must decline honestly -- naming the language -- and an
    undetected language must not become English either. Runs through the
    REAL `spacy_ner`/`spacy_svo` code (a fake `spacy` module stands in for
    the installed-package check and `spacy.load`, so no model download is
    needed), not the `ner_fn`/`svo_fn` stubs the rest of this file uses.
    """

    @pytest.fixture
    def fake_spacy(self, monkeypatch):
        import sys
        import types

        from fichero_server.knowledge import spacy_ner

        spacy_ner._pipelines.clear()
        loaded: list[str] = []
        installed: set[str] = set()

        module = types.ModuleType("spacy")
        util = types.ModuleType("spacy.util")
        util.get_installed_models = lambda: sorted(installed)  # type: ignore[attr-defined]
        module.util = util  # type: ignore[attr-defined]

        def _load(name: str):
            # The whole point of this fixture: fail LOUD if anything ever
            # asks for an English model in a test that must never load one.
            if name.startswith("en_"):
                raise AssertionError(f"must never load an English model, got {name!r}")
            if name not in installed:
                raise OSError(f"[E050] Can't find model {name!r}")
            loaded.append(name)
            return object()

        module.load = _load  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "spacy", module)
        monkeypatch.setitem(sys.modules, "spacy.util", util)
        yield installed, loaded
        spacy_ner._pipelines.clear()

    def test_unsupported_known_language_declines_and_never_loads_english(
        self, db, test_package, fake_spacy
    ):
        """A document in a real, KNOWN language spaCy has NO model family for
        at all (Latin -- not merely 'not installed', genuinely absent from
        `_MODEL_PREFERENCE`, exactly the issue's own example) declines with
        a reason naming Latin -- never a silent English substitution."""
        _installed, loaded = fake_spacy
        doc = Document(
            name="la.md", doc_type=DocType.file, file_type=FileType.text,
            status=Status.pending,
            page_content="Notarius instrumentum coram testibus signavit.",
            language="Latin",
        )
        db.save(doc)

        def _fail_if_called(*a, **kw):
            raise AssertionError("must not run NER once the language is known unsupported")

        result = run_nlp_draft(
            db, doc, ner_fn=_fail_if_called, svo_fn=_fail_if_called, filter_fn=_fail_if_called,
        )

        assert result.error is not None
        assert "Latin" in result.error
        assert result.entity_ids == []
        assert result.claim_ids == []
        assert loaded == []  # nothing was ever loaded -- declined before trying

    def test_undetected_language_does_not_become_english(
        self, db, test_package, monkeypatch, fake_spacy
    ):
        """A document whose language genuinely could not be determined must
        decline -- never silently resolve to English and proceed."""
        from fichero_server.llm import language_policy

        _installed, loaded = fake_spacy

        def _undetermined(*, requested=None, document=None, text="", **kw):
            return language_policy.LanguageResolution(
                language=None, status=language_policy.UNKNOWN,
                source="test", basis="document language could not be determined (test)",
            )

        monkeypatch.setattr(language_policy, "resolve_language", _undetermined)
        doc = _text_doc(db, text="Some page with no determinable language signal.")

        def _fail_if_called(*a, **kw):
            raise AssertionError("must not run NER when the language is undetermined")

        result = run_nlp_draft(
            db, doc, ner_fn=_fail_if_called, svo_fn=_fail_if_called, filter_fn=_fail_if_called,
        )

        assert result.error is not None
        assert "en" not in result.error.split()
        assert result.entity_ids == []
        assert result.claim_ids == []
        assert loaded == []

    def test_a_supported_language_still_works_through_the_real_pipeline(
        self, db, test_package, fake_spacy, monkeypatch
    ):
        """Regression guard: the decline path must not have broken the
        normal case. Spanish, installed, no NER/SVO stubs -- the real
        `spacy_ner.extract_entities`/`spacy_svo.propose_triples` run,
        against a fake `es` spaCy pipeline standing in for the real model."""
        import types

        installed, loaded = fake_spacy
        installed.add("es_core_news_sm")

        # A minimal fake spaCy Language callable: returns an object with a
        # `.ents` list carrying one PERSON span, matching what
        # `spacy_ner.extract_entities` reads off `nlp(text)`.
        class _FakeSpan:
            def __init__(self, text, label, start, end):
                self.text = text
                self.label_ = label
                self.start_char = start
                self.end_char = end

        class _FakeDoc:
            def __init__(self, ents):
                self.ents = ents

        class _FakeNLP:
            def __call__(self, text):
                idx = text.index("Juan Perez")
                return _FakeDoc([_FakeSpan("Juan Perez", "PER", idx, idx + len("Juan Perez"))])

        import sys

        real_load = sys.modules["spacy"].load

        def _load_with_fake_pipeline(name):
            real_load(name)  # still exercises the installed-check/load path
            return _FakeNLP()

        monkeypatch.setattr(sys.modules["spacy"], "load", _load_with_fake_pipeline)

        doc = Document(
            name="es.md", doc_type=DocType.file, file_type=FileType.text,
            status=Status.pending, page_content="Juan Perez firmó la escritura.",
            language="es",
        )
        db.save(doc)

        def _no_triples(text, language=None):
            return []

        result = run_nlp_draft(db, doc, svo_fn=_no_triples, filter_fn=lambda proposals, text: ([], []))

        assert result.error is None
        assert result.entity_ids
        entity = db.get(KnowledgeEntity, result.entity_ids[0])
        assert entity.canonical_name == "Juan Perez"
        assert loaded == ["es_core_news_sm"]


class TestNlpStageInDerivatives:
    def test_missing_model_records_visible_metadata_never_flips_processed(
        self, db, test_package, monkeypatch
    ):
        from fichero_server.knowledge import spacy_ner

        monkeypatch.setattr(spacy_ner, "is_pipeline_available", lambda lang: False)
        doc = _text_doc(db)

        derivatives._nlp_stage(doc.id, test_package)

        after = db.get(Document, doc.id)
        assert "nlp_error" in after.metadata
        assert "not installed" in after.metadata["nlp_error"]
        assert "nlp_processed_at" not in after.metadata

    def test_success_sets_processed_marker_and_clears_prior_error(
        self, db, test_package, monkeypatch
    ):
        doc = _text_doc(db)
        doc.metadata = {"nlp_error": "stale from a previous failed run"}
        db.save(doc)
        monkeypatch.setattr(
            "fichero_server.importers.nlp_draft.run_nlp_draft",
            lambda db_, doc_, **kw: NlpDraftResult(entity_ids=["e1"], claim_ids=["c1"]),
        )

        derivatives._nlp_stage(doc.id, test_package)

        after = db.get(Document, doc.id)
        assert "nlp_processed_at" in after.metadata
        assert "nlp_error" not in after.metadata

    def test_already_processed_document_is_skipped(self, db, test_package, monkeypatch):
        doc = _text_doc(db)
        doc.metadata = {"nlp_processed_at": "2026-01-01T00:00:00+00:00"}
        db.save(doc)

        def _fail_if_called(*a, **kw):
            raise AssertionError("must not re-run NLP on an already-processed document")

        monkeypatch.setattr(
            "fichero_server.importers.nlp_draft.run_nlp_draft", _fail_if_called
        )

        derivatives._nlp_stage(doc.id, test_package)  # must not raise


# =============================================================================
# Settings: OFF means not queued at all.
# =============================================================================


class TestSettingGatesQueueing:
    def test_default_is_off_for_now(self, db, test_package):
        """Temporary manager decision (S1, team-lead review): the ruling's
        default is ON, but there is no Settings row yet and no way to take
        rows back -- unset means OFF until both exist. See
        `nlp_draft._DEFAULT_ENABLED`'s docstring."""
        from fichero_server.db.app import get_app_db

        get_app_db().delete_setting(AUTO_NLP_SETTING_KEY)

        assert auto_nlp_enabled() is False

    def test_explicit_on_setting_is_read(self, db, test_package):
        from fichero_server.db.app import get_app_db

        get_app_db().set_setting(AUTO_NLP_SETTING_KEY, "true")
        try:
            assert auto_nlp_enabled() is True
        finally:
            get_app_db().delete_setting(AUTO_NLP_SETTING_KEY)

    def test_explicit_off_setting_is_read(self, db, test_package):
        from fichero_server.db.app import get_app_db

        get_app_db().set_setting(AUTO_NLP_SETTING_KEY, "false")
        try:
            assert auto_nlp_enabled() is False
        finally:
            get_app_db().delete_setting(AUTO_NLP_SETTING_KEY)

    def test_setting_off_queues_no_nlp_stage(self, db, test_package, monkeypatch):
        # Stub the real embed stage -- this doc's page_content makes it
        # embedding-eligible too, and the real embedder pays a real
        # first-model-load cost this test has no interest in (slow-test
        # fix, team-lead review).
        monkeypatch.setattr(type(db), "embed", lambda self, d: True)
        monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: False)
        called = []
        monkeypatch.setattr(
            derivatives, "_nlp_stage", lambda *a, **kw: called.append(a)
        )
        doc = _text_doc(db)

        futures = derivatives.queue_derivatives([doc], library_path=test_package)
        _drain(futures)

        assert called == []

    def test_setting_on_queues_the_nlp_stage(self, db, test_package, monkeypatch):
        monkeypatch.setattr(type(db), "embed", lambda self, d: True)
        monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: True)
        called = []
        monkeypatch.setattr(
            derivatives, "_nlp_stage", lambda doc_id, library: called.append(doc_id)
        )
        doc = _text_doc(db)

        futures = derivatives.queue_derivatives([doc], library_path=test_package)
        _drain(futures)

        assert called == [doc.id]


# =============================================================================
# Safety: only new/stranded-pending documents, never an existing library's
# already-completed documents.
# =============================================================================


class TestExistingLibrariesAreNotSwept:
    def test_needs_nlp_matches_needs_embedding_population(self, db, test_package):
        text_doc = Document(name="a.md", doc_type=DocType.file, file_type=FileType.text, page_content="hi")
        blank_doc = Document(name="a.zip", doc_type=DocType.file, file_type=FileType.other)
        assert needs_nlp(text_doc)
        assert not needs_nlp(blank_doc)

    def test_opening_a_library_with_only_completed_docs_queues_nothing(
        self, db, test_package, monkeypatch
    ):
        from fichero_server.db.manager import db_manager

        doc = _text_doc(db)
        doc.status = Status.completed
        db.save(doc)

        called = []
        monkeypatch.setattr(
            "fichero_server.importers.derivatives.queue_derivatives",
            lambda *a, **kw: called.append(a) or [],
        )
        monkeypatch.delenv("FICHERO_SKIP_DERIVATIVE_RESUME", raising=False)

        db_manager.close_database(test_package)
        db_manager.get_database(test_package)

        assert called == []


# =============================================================================
# Curation persists and constrains a later/re-run (curation-persists-and-
# constrains-imports).
# =============================================================================


class TestCurationSurvivesAndConstrains:
    def test_a_human_reviewed_entity_is_not_reset_or_duplicated_by_a_rerun(
        self, db, test_package
    ):
        doc = _text_doc(db)
        first = run_nlp_draft(db, doc, **_stubs())
        entity = db.get(KnowledgeEntity, first.entity_ids[0])
        entity.curation_state = EntityCurationState.verified
        db.save(entity)

        second = run_nlp_draft(db, doc, **_stubs())

        assert db.query(KnowledgeEntity, canonical_name="Juan Perez").__len__() == 1
        refreshed = db.get(KnowledgeEntity, entity.id)
        assert refreshed.curation_state == EntityCurationState.verified
        # The re-run's own claim identity match should land on the SAME
        # claim row too, not a second one.
        assert set(second.entity_ids) == {entity.id}

    def test_a_claim_suppression_rule_prunes_the_draft_before_it_is_written(
        self, db, test_package
    ):
        """A suppression rule targets ONE predicate (the SVO claim); the
        entity section's own "X is a <type>" claim is a separate write and
        is untouched by a rule that doesn't match it -- this proves the
        rule is respected, not that every claim vanishes."""
        db.save(
            ClaimSuppressionRule(
                action=ClaimSuppressionRuleAction.prune,
                match_predicate_verb="firmó",
                reason="not useful — test fixture",
            )
        )
        doc = _text_doc(db)

        run_nlp_draft(db, doc, **_stubs())

        claims = db.query(KnowledgeClaim, source_document_id=doc.id)
        assert not any(c.svo_verb == "firmó" for c in claims)
        assert not any("escritura" in (c.text or "") for c in claims)


# =============================================================================
# Idempotency: identical proposals on a second run never duplicate rows
# (team-lead: "I will not rely on an unverified dedup" -- verify it here).
# =============================================================================


class TestWriterIdempotency:
    def test_the_same_page_proposed_twice_does_not_duplicate_rows(self, db, test_package):
        doc = _text_doc(db)

        first = run_nlp_draft(db, doc, **_stubs())
        first_claim_count = len(db.query(KnowledgeClaim, source_document_id=doc.id))
        first_entity_count = len(db.query(KnowledgeEntity, canonical_name="Juan Perez"))

        second = run_nlp_draft(db, doc, **_stubs())

        assert len(db.query(KnowledgeEntity, canonical_name="Juan Perez")) == first_entity_count
        assert len(db.query(KnowledgeClaim, source_document_id=doc.id)) == first_claim_count
        assert set(first.entity_ids) == set(second.entity_ids)
        assert set(first.claim_ids) == set(second.claim_ids)


# =============================================================================
# Coalesced change event: once per document, never per row.
# =============================================================================


class TestChangeEventIsCoalescedOncePerDocument:
    def test_one_call_for_the_whole_document(self, db, test_package, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "fichero_server.workflows.tools._workflow_change_emit.emit_workflow_kg_changes_for_db",
            lambda *a, **kw: calls.append((a, kw)),
        )
        doc = _text_doc(db)

        result = run_nlp_draft(db, doc, **_stubs())

        assert len(calls) == 1
        _args, kwargs = calls[0]
        assert kwargs["document_ids"] == [doc.id]
        assert set(kwargs["entity_ids"]) == set(result.entity_ids)
        assert set(kwargs["claim_ids"]) == set(result.claim_ids)

    def test_no_event_when_nothing_was_written(self, db, test_package, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "fichero_server.workflows.tools._workflow_change_emit.emit_workflow_kg_changes_for_db",
            lambda *a, **kw: calls.append((a, kw)),
        )
        doc = _text_doc(db, text="   ")

        run_nlp_draft(db, doc, **_stubs())

        assert calls == []


# =============================================================================
# Shares the derivatives module's bounded, background-QoS executor -- no new
# pool, so the [[user-machine-always-useful]] throttle already proven for
# thumbnails/embeds covers this stage too.
# =============================================================================


class TestSharesTheBoundedExecutor:
    def test_nlp_stage_runs_on_the_same_executor_as_thumbnails_and_embeds(
        self, db, test_package, monkeypatch
    ):
        seen_executors = []
        real_get_executor = derivatives._get_executor

        def _spy():
            executor = real_get_executor()
            seen_executors.append(executor)
            return executor

        # This test is about WHICH POOL each stage runs on, not extraction
        # quality or embedding correctness -- stub both real model-backed
        # stages so it doesn't pay a real cold-start (slow-test fix, team-
        # lead review).
        monkeypatch.setattr(type(db), "embed", lambda self, d: True)
        monkeypatch.setattr(
            "fichero_server.importers.nlp_draft.run_nlp_draft",
            lambda db_, doc_, **kw: NlpDraftResult(),
        )
        monkeypatch.setattr(derivatives, "_get_executor", _spy)
        monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: True)
        doc = _text_doc(db)

        futures = derivatives.queue_derivatives([doc], library_path=test_package)
        _drain(futures)

        assert len({id(e) for e in seen_executors}) == 1
        assert derivatives.MAX_CONCURRENT_DERIVATIVES == 2  # unchanged ceiling


# =============================================================================
# One real-pipeline test -- skips, visibly, when the model isn't installed.
# =============================================================================


def _es_model_installed() -> bool:
    try:
        from fichero_server.knowledge import spacy_ner

        return spacy_ner.is_pipeline_available("es")
    except Exception:
        return False


@pytest.mark.skipif(
    not _es_model_installed(),
    reason="es_core_news_sm not installed on this machine — real-pipeline test skipped",
)
class TestRealSpacyPipeline:
    def test_a_real_page_produces_a_person_entity(self, db, test_package):
        doc = _text_doc(
            db, text="Juan Perez vendió una casa a Maria Lopez en la ciudad de Sevilla."
        )

        result = run_nlp_draft(db, doc)

        assert result.error is None
        entities = db.query(KnowledgeEntity, entity_type=EntityType.person)
        assert entities
