"""A project can declare a language or script no registry has (#4938).

`source.lang.project-declared`. The behavior is one sentence and the interesting
part is what it implies: a code no registry has is meaningless unless the library
records what it means, so a declaration is a code AND a name, and a private-use
code without one must be refused rather than stored.

The two halves are tested differently on purpose, because they ARE different:
a script is stored as a code and needs the record; a language is stored as a
canonical name (``Document.language``, #2092), so the declaration and the value
are the same string and no record exists to test. See the module docstring of
``models/source_declarations.py``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.db import Database
from fichero_server.llm.language_policy import (
    LEVEL_DOCUMENT,
    LEVEL_PROJECT,
    LEVEL_SEGMENT,
    SOURCE_DERIVED_FROM_SCRIPT,
    resolve_direction,
    resolve_script,
)
from fichero_server.models.source_declarations import (
    ENCODING_FULL,
    ENCODING_NONE,
    ENCODING_PART,
    CannotDeclareRegisteredScript,
    DeclarationNeedsAName,
    UnknownEncoding,
    UnknownProjectFact,
    UnknownScript,
    assert_known_script,
    declare_script,
    language_is_project_declared,
    library_scripts,
    name_registered_script,
    clear_project_fact,
    project_facts,
    project_setting_id,
    resolve_encoding,
    set_project_fact,
    script_code_is_well_formed,
    script_display_name,
    script_row,
)

import fichero_server.api.routes.document.content_representations  # noqa: F401

pytestmark = pytest.mark.source_model


@pytest.fixture
def library(tmp_path):
    """A library of this test's own: declarations are per-library facts, and a
    shared fixture library would carry one test's declared script into the next
    one's refusal."""
    db = Database(tmp_path / "declared.duckdb")
    try:
        yield db
    finally:
        db.close()


class TestDeclaringAScript:
    def test_a_project_declares_a_script_no_registry_has(self, library):
        row = declare_script(library, "Qaaa", "The Marshall hand")

        assert row.code == "Qaaa"
        assert row.name == "The Marshall hand"
        assert row.declared is True
        # And it is a row in the library, not a value held in memory by whoever
        # declared it: the next reader of a stored `Qaaa` can find out what it is.
        assert script_display_name(library, "Qaaa") == "The Marshall hand"

    def test_the_declaration_survives_a_reopen(self, tmp_path):
        path = tmp_path / "reopen.duckdb"
        first = Database(path)
        try:
            declare_script(first, "Qaab", "Chancery abbreviations")
        finally:
            first.close()

        second = Database(path)
        try:
            assert script_display_name(second, "Qaab") == "Chancery abbreviations"
        finally:
            second.close()

    def test_declaring_twice_updates_one_row_and_does_not_make_two(self, library):
        first = declare_script(library, "Qaaa", "The Marshal hand")
        second = declare_script(library, "Qaaa", "The Marshall hand", encoding=ENCODING_PART)

        assert second.id == first.id, "a second declaration made a second row"
        rows = [row for row in library_scripts(library) if row.code == "Qaaa"]
        assert len(rows) == 1
        # Two rows would mean a stored value with two meanings, which is worse
        # than a typo in the name.
        assert rows[0].name == "The Marshall hand"
        assert rows[0].encoding == ENCODING_PART

    def test_a_declaration_needs_a_name(self, library):
        with pytest.raises(DeclarationNeedsAName):
            declare_script(library, "Qaaa", "   ")
        assert script_row(library, "Qaaa") is None, "the refused declaration was stored"

    def test_a_project_may_not_redefine_a_registered_script(self, library):
        with pytest.raises(CannotDeclareRegisteredScript) as raised:
            declare_script(library, "Latn", "our own Latin")

        # The message has to point at the way out, or the caller invents one.
        assert "private-use" in str(raised.value)
        assert script_row(library, "Latn") is None

    def test_an_encoding_outside_the_three_values_is_refused(self, library):
        with pytest.raises(UnknownEncoding):
            declare_script(library, "Qaaa", "The Marshall hand", encoding="partial")

    def test_encoding_is_unset_until_someone_establishes_it(self, library):
        """`unknown-is-not-unexamined` for the third fact: nothing here guesses
        an encoding from the code, and an absent one is not `none`."""
        row = declare_script(library, "Qaaa", "The Marshall hand")
        assert row.encoding is None
        assert ENCODING_NONE != row.encoding


class TestNamingARegisteredScript:
    def test_a_library_can_name_a_registered_script_without_declaring_it(self, library):
        row = name_registered_script(library, "Arab", "Arabic", encoding=ENCODING_PART)

        assert row.declared is False
        assert script_display_name(library, "Arab") == "Arabic"

    def test_naming_refuses_a_private_use_code(self, library):
        """The two calls are not interchangeable: a `Qaaa` row with
        `declared=False` would claim a registry entry that does not exist."""
        with pytest.raises(CannotDeclareRegisteredScript):
            name_registered_script(library, "Qaaa", "The Marshall hand")


class TestRefusingAScriptValue:
    def test_an_undeclared_private_use_code_is_refused(self, library):
        with pytest.raises(UnknownScript) as raised:
            assert_known_script(library, "Qaaa")

        assert "has not declared" in str(raised.value)
        assert "and a name" in str(raised.value), "the refusal does not say how to declare one"

    def test_the_same_code_passes_once_it_is_declared(self, library):
        declare_script(library, "Qaaa", "The Marshall hand")
        assert_known_script(library, "Qaaa")  # no raise

    @pytest.mark.parametrize("code", ["latn", "LATN", "Lat", "Latin", "Zx", "", "12ab"])
    def test_a_malformed_code_is_refused(self, library, code):
        with pytest.raises(UnknownScript):
            assert_known_script(library, code)

    @pytest.mark.parametrize("code", ["Latn", "Arab", "Hani", "Zxxx", "Zyyy", "Zzzz"])
    def test_a_well_formed_registered_code_passes(self, library, code):
        assert_known_script(library, code)

    def test_a_code_the_engine_cannot_confirm_passes_and_that_is_deliberate(self, library):
        """Fichero ships no copy of ISO 15924, so `Lxtn` cannot be told from
        `Latn` offline. Passing it is honest; refusing every unconfirmable code
        would refuse real scripts, and a short hand-kept list would look
        authoritative while being wrong. The refusal that carries weight is the
        private-use one, which is the one this behavior needs."""
        assert_known_script(library, "Lxtn")

    def test_a_reading_stored_under_a_since_removed_declaration_still_reads(self, library):
        """The reading-kinds rule, applied here: writes are checked, reads never
        are. A project that tidies its declarations must not lose the text."""
        declare_script(library, "Qaaa", "The Marshall hand")
        row = script_row(library, "Qaaa")
        assert row is not None
        library.delete(row)

        # The value is now unusable for a NEW write...
        with pytest.raises(UnknownScript):
            assert_known_script(library, "Qaaa")
        # ...and nothing about reading it back was touched: `script_display_name`
        # says it cannot name the code rather than raising.
        assert script_display_name(library, "Qaaa") is None


class TestTheShapeCheck:
    @pytest.mark.parametrize(
        "code,well_formed",
        [("Latn", True), ("Qaaa", True), ("Zxxx", True), ("latn", False), ("Lat", False)],
    )
    def test_iso_15924_shape(self, code, well_formed):
        assert script_code_is_well_formed(code) is well_formed


class TestTheLanguageHalf:
    @pytest.mark.parametrize("value", ["qaa", "qtz", "qaa-Latn", "es-x-marshall", "QAA"])
    def test_a_private_use_tag_reads_as_the_projects_own(self, value):
        assert language_is_project_declared(value) is True

    @pytest.mark.parametrize("value", ["es", "es-MX", "qua", "quz", "", None, "Spanish"])
    def test_a_registered_tag_or_a_name_does_not(self, value):
        assert language_is_project_declared(value) is False

    def test_a_canonical_name_is_not_a_claim_about_a_registry(self):
        """The asymmetry stated plainly. `Document.language` holds a NAME, so a
        project working in an unregistered language already writes that name and
        the cascade carries it — there is nothing to declare and nowhere to
        declare it. `language_is_project_declared` answers a narrower question:
        is this value a private-use TAG. A name is neither declared nor
        registered, and saying False is the honest answer to a question that
        does not apply."""
        assert language_is_project_declared("Chinantec of San Juan") is False

    def test_no_language_table_exists_beside_the_name(self):
        """Pins the decision, so a later change of mind is deliberate: there is
        no `LibraryLanguage`. If one is ever added, this test fails and whoever
        added it has to say why two places should hold one fact."""
        import fichero_server.models.source_declarations as module

        assert not hasattr(module, "LibraryLanguage")


class TestTheRefusalIsLive:
    """A refusal nothing calls is a comment. These go through the REAL action.

    Uses the shared library, not this module's own, because that is where the
    action registry writes. Each test names a distinct code so a declaration
    made here cannot make another test's refusal pass.
    """

    def _create(self, db, **extra):
        return registry.invoke(
            db,
            "representation.create",
            {
                "document_id": "doc-declared-scripts",
                "kind": "transcription",
                "content": "en el nombre de dios",
                **extra,
            },
            ActionContext(actor="historian", is_bootstrap=True),
        )

    def test_a_reading_cannot_be_written_in_an_undeclared_private_use_script(self, db):
        with pytest.raises(UnknownScript):
            self._create(db, script="Qabx")

    def test_it_can_once_the_project_declares_it(self, db):
        declare_script(db, "Qabw", "The Marshall hand")

        result = self._create(db, script="Qabw")
        reading_id = result["representation_id"] if isinstance(result, dict) else result
        assert reading_id

    def test_a_registered_script_needs_no_declaration(self, db):
        assert self._create(db, script="Latn")

    def test_a_reading_with_no_script_is_untouched(self, db):
        """Most readings say nothing about script, and `unknown-is-not-
        unexamined` means saying nothing must stay possible."""
        assert self._create(db)


class TestADeclaredScriptResolves:
    """The spec's own test for this behavior: "a declared script resolves and an
    undeclared private code is refused". The refusal is above; this is the other
    half, and it is what makes a declaration worth making — the cascade must
    carry a project's code exactly as it carries `Latn`."""

    def test_a_declared_code_resolves_through_the_cascade_with_its_level(self, library):
        declare_script(library, "Qaaa", "The Marshall hand")
        segment = SimpleNamespace(script="Qaaa", script_meta={"source": "user"})

        resolved = resolve_script(segment=segment)

        assert resolved.language == "Qaaa"
        assert resolved.is_known
        assert resolved.level == LEVEL_SEGMENT
        # And the library can say what the code means, which is the difference
        # between a declared script and an unreadable value.
        assert script_display_name(library, resolved.language) == "The Marshall hand"

    def test_the_cascade_does_not_consult_the_declarations_at_all(self, library):
        """Deliberate: `resolve_script` takes no `db`. Resolution answers "what
        does this record say"; the declaration answers "what does that mean".
        Making the walk check the table would turn a missing declaration into a
        missing script, and lose stored text to a tidy-up."""
        segment = SimpleNamespace(script="Qabx", script_meta={})

        resolved = resolve_script(segment=segment)

        assert resolved.language == "Qabx"
        assert script_display_name(library, "Qabx") is None


class TestEncodingIsTheScriptsAndIsReadNotStored:
    """Ruled 2026-09-26: encoding is ONE fact at two levels. The script row holds
    it; a page's encoding is its script's, read through the same cascade."""

    def test_a_segments_encoding_is_read_from_its_scripts_row(self, library):
        name_registered_script(library, "Arab", "Arabic", encoding=ENCODING_PART)
        segment = SimpleNamespace(script="Arab", script_meta={})

        resolved = resolve_encoding(library, segment=segment)

        assert resolved.language == ENCODING_PART
        assert resolved.is_known
        # No rung stated it -- the script row supplied it -- so the SOURCE
        # carries that and the level is None. A derivation is a way of
        # determining, not a place in the cascade.
        assert resolved.source == SOURCE_DERIVED_FROM_SCRIPT
        assert resolved.level is None
        assert "Arab" in resolved.basis

    def test_it_really_reads_the_row_and_not_a_guess_from_the_code(self, library):
        """The test the ruling asked for: prove the answer comes from the row.
        The same script code gives two different answers when the row changes,
        which nothing derived from the code itself could do."""
        name_registered_script(library, "Arab", "Arabic", encoding=ENCODING_PART)
        segment = SimpleNamespace(script="Arab", script_meta={})
        assert resolve_encoding(library, segment=segment).language == ENCODING_PART

        name_registered_script(library, "Arab", "Arabic", encoding=ENCODING_FULL)
        assert resolve_encoding(library, segment=segment).language == ENCODING_FULL

    def test_it_follows_the_cascade_so_a_readings_script_wins(self, library):
        declare_script(library, "Qaaa", "The clerk's hand", encoding=ENCODING_NONE)
        name_registered_script(library, "Latn", "Latin", encoding=ENCODING_FULL)

        resolved = resolve_encoding(
            library,
            reading=SimpleNamespace(script="Qaaa", script_meta={}),
            segment=SimpleNamespace(script="Latn", script_meta={}),
        )

        # `reading-overrides` reaches the third fact for free, because encoding
        # does not walk its own cascade -- it reads whatever the script walk won.
        assert resolved.language == ENCODING_NONE

    def test_no_script_established_is_not_the_same_as_unencodable(self, library):
        resolved = resolve_encoding(library, segment=SimpleNamespace(script=None, script_meta={}))

        assert resolved.language is None
        assert resolved.is_known is False
        assert "no script is established" in resolved.basis
        # `none` is the positive claim that a writing system cannot be encoded.
        # Returning it here would answer a question nobody asked.
        assert resolved.language != ENCODING_NONE

    def test_a_known_script_with_no_recorded_encoding_says_exactly_that(self, library):
        segment = SimpleNamespace(script="Hebr", script_meta={})

        resolved = resolve_encoding(library, segment=segment)

        assert resolved.is_known is False
        assert "has not recorded an encoding for Hebr" in resolved.basis
        # Three distinguishable states, not two: unknown-because-no-script,
        # unknown-because-not-established, and the positive `none`.
        assert resolved.basis != resolve_encoding(
            library, segment=SimpleNamespace(script=None, script_meta={})
        ).basis

    def test_the_answer_is_unchanged_when_no_model_is_configured_at_all(self, library):
        """THE TEST THAT WOULD FAIL if someone later "optimised" this into
        `llm/script_coverage.py`. That module needs a tokenizer, so a library
        with no model configured would suddenly answer differently — and an
        archival fact that changes meaning when you swap a model is not an
        archival fact. Encoding is page-against-Unicode, never
        model-against-tokenizer.
        """
        name_registered_script(library, "Arab", "Arabic", encoding=ENCODING_PART)
        segment = SimpleNamespace(script="Arab", script_meta={})

        with_nothing_configured = resolve_encoding(library, segment=segment)

        assert with_nothing_configured.language == ENCODING_PART
        assert with_nothing_configured.source == SOURCE_DERIVED_FROM_SCRIPT
        # And no tokenizer, model catalogue or provider was consulted to say so:
        # the only input was the row this test wrote.
        assert "model" not in with_nothing_configured.basis

    def test_an_unwritten_script_is_not_special_cased(self, library):
        """`Zxxx` (unwritten) is a fourth state again: the question does not
        arise. It resolves like any other code and the library's own row is where
        that gets said — inventing an answer here would be the guess the three
        unknowns exist to avoid."""
        resolved = resolve_encoding(library, segment=SimpleNamespace(script="Zxxx", script_meta={}))
        assert resolved.is_known is False

        name_registered_script(library, "Zxxx", "Unwritten (a recording)", encoding=ENCODING_NONE)
        assert resolve_encoding(
            library, segment=SimpleNamespace(script="Zxxx", script_meta={})
        ).language == ENCODING_NONE


class TestTheProjectRung:
    """The project level of the three facts (`source.lang.cascade`).

    Stored as the library's own `LibrarySetting` rows and read back as a HOLDER
    the existing cascade walks, so adding a rung cost the resolvers one line each
    rather than a second way of reading a fact.
    """

    def test_a_project_states_a_script_and_a_segment_inherits_it(self, library):
        set_project_fact(library, "script", "Arab")

        resolved = resolve_script(
            segment=SimpleNamespace(script=None, script_meta=None),
            project=project_facts(library),
        )

        assert resolved.language == "Arab"
        assert resolved.level == LEVEL_PROJECT

    def test_a_segment_overrides_the_project(self, library):
        set_project_fact(library, "script", "Arab")

        resolved = resolve_script(
            segment=SimpleNamespace(script="Latn", script_meta=None),
            project=project_facts(library),
        )

        assert resolved.language == "Latn"
        assert resolved.level == LEVEL_SEGMENT

    def test_the_project_is_the_last_rung_and_not_the_first(self, library):
        """Ordering matters and this pins it: a project value is a DEFAULT for
        everything under it, so it must be read after every more specific level,
        not before."""
        set_project_fact(library, "script", "Arab")

        resolved = resolve_script(
            document=SimpleNamespace(script="Hebr", script_meta=None),
            segment=SimpleNamespace(script=None, script_meta=None),
            project=project_facts(library),
        )

        assert resolved.language == "Hebr"
        assert resolved.level == LEVEL_DOCUMENT

    def test_a_project_direction_is_inherited_before_anything_is_derived(self, library):
        """The derivation is the LAST resort, below every stated level. A project
        that says `ttb` must not be overruled by a script table."""
        set_project_fact(library, "direction", "ttb")

        resolved = resolve_direction(
            segment=SimpleNamespace(script="Arab", direction=None, direction_meta=None),
            project=project_facts(library),
        )

        assert resolved.language == "ttb"
        assert resolved.level == LEVEL_PROJECT
        assert resolved.source != SOURCE_DERIVED_FROM_SCRIPT

    def test_a_project_that_states_nothing_falls_through(self, library):
        facts = project_facts(library)

        assert facts.states_nothing
        resolved = resolve_script(
            segment=SimpleNamespace(script=None, script_meta=None), project=facts
        )
        assert resolved.is_known is False

    def test_the_provenance_the_caller_recorded_is_what_reads_back(self, library):
        set_project_fact(
            library, "language", "Spanish", meta={"source": "user", "status": "known"}
        )

        resolved = resolve_script(project=project_facts(library))
        assert resolved.is_known is False, "a language setting is not a script setting"

        facts = project_facts(library)
        assert facts.language == "Spanish"
        assert facts.language_meta["source"] == "user"

    def test_clearing_removes_the_row_rather_than_writing_an_empty_one(self, library):
        from fichero_server.models.knowledge import LibrarySetting

        set_project_fact(library, "script", "Arab")
        assert library.get(LibrarySetting, project_setting_id("script")) is not None

        clear_project_fact(library, "script")

        # An empty row would be the project saying "I considered this and have
        # nothing to say", which is a claim. Absence is the honest state.
        assert library.get(LibrarySetting, project_setting_id("script")) is None
        assert project_facts(library).script is None

    def test_an_unreadable_row_is_ignored_on_READ_and_refused_on_WRITE(self, library):
        """A settings table is shared with every other programme. One row written
        by a different build must not make a page unreadable — but a bad key from
        a caller is refused where somebody can still fix it."""
        from fichero_server.models.knowledge import LibrarySetting

        library.save(LibrarySetting(id=project_setting_id("script"), value="not json"))
        assert project_facts(library).script is None  # ignored, not raised

        with pytest.raises(UnknownProjectFact):
            set_project_fact(library, "encoding", "full")

    def test_a_project_script_reaches_the_encoding_read(self, library):
        """The three facts compose: a project-stated script is what the encoding
        read looks up, so a library can answer "how much of this can we encode"
        with nothing set on any page."""
        name_registered_script(library, "Arab", "Arabic", encoding=ENCODING_PART)
        set_project_fact(library, "script", "Arab")

        resolved = resolve_encoding(library, project=project_facts(library))

        assert resolved.language == ENCODING_PART
