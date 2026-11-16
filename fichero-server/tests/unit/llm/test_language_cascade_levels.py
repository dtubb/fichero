"""Source-model slice 9 (#4938) — `source.lang.says-where-from` for the resolver.

Spec: `languages-scripts-signs.md`. Slice 9 item 2 made a READING able to record
where its language came from; this is the resolver half — `LanguageResolution`
gains `level`, and the cascade gains a SEGMENT rung between a pinned request and
the document.

**THE FIELD IS THE RUNG THE ANSWER CAME FROM, NOT THE RUNG THAT ASKED.** A
caller resolving for a segment that states nothing gets `LEVEL_DOCUMENT` back,
because that is where the value was found — the caller already knows what it
asked about. `test_a_fallback_reports_the_rung_it_came_from_not_the_one_that_asked`
is the test that fails if that is ever inverted, and it is the reason the field
exists.

`level=None` means NOT STATED and never "unknown": `STATUS_UNKNOWN` carries
unknown, and a resolution can be unknown while still saying which rung
established it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.llm.language_policy import (
    LEVEL_DOCUMENT,
    LEVEL_PROJECT,
    LEVEL_READING,
    LEVEL_SEGMENT,
    LanguagePolicy,
    LanguageResolution,
    STATUS_UNKNOWN,
    resolve_language,
)

pytestmark = pytest.mark.source_model

DOCUMENT_POLICY = LanguagePolicy(mode="document")


def _document(language=None, *, source="user", status="known"):
    meta = None if language is None and status == "known" else {
        "status": status, "source": source
    }
    return SimpleNamespace(language=language, language_meta=meta)


def _segment(language=None, *, source="user", status=None):
    meta = {"status": status, "source": source} if status else None
    return SimpleNamespace(language=language, language_meta=meta)


class TestTheLevelIsTheRungTheAnswerCameFrom:
    def test_a_fallback_reports_the_rung_it_came_from_not_the_one_that_asked(self):
        """THE CONDITION on this field, and the reason it exists.

        A caller asks about a SEGMENT. The segment states nothing, so the answer
        comes from the document — and `level` must say `document`. Reporting
        `segment` (the rung that asked) would make the field useless while
        looking correct, because every answer would echo the question.
        """
        resolution = resolve_language(
            document=_document("es"),
            segment=_segment(),  # states nothing
            policy=DOCUMENT_POLICY,
            detect=False,
        )

        assert resolution.language == "es"
        assert resolution.level == LEVEL_DOCUMENT, (
            "a value found on the document must report the document, not the "
            "segment that was asked about"
        )
        assert resolution.level != LEVEL_SEGMENT

    def test_a_segment_that_states_its_own_language_reports_the_segment(self):
        resolution = resolve_language(
            document=_document("es"),
            segment=_segment("la"),
            policy=DOCUMENT_POLICY,
            detect=False,
        )

        # `many-per-page`: the region's own answer wins over the page's, and
        # says so.
        assert resolution.language == "la"
        assert resolution.level == LEVEL_SEGMENT

    def test_the_project_policy_reports_the_project(self):
        resolution = resolve_language(
            policy=LanguagePolicy(mode="one", languages=("es",)), detect=False
        )
        assert resolution.language == "es"
        assert resolution.level == LEVEL_PROJECT

    def test_a_pinned_request_states_no_level(self):
        """A language typed into this run is not inherited from any rung, so
        `None` — not stated — is the honest answer rather than inventing a
        fifth level for "the caller"."""
        resolution = resolve_language(requested="fr")
        assert resolution.language == "fr"
        assert resolution.level is None

    def test_a_project_refusing_the_documents_answer_reports_the_project(self):
        """An UNKNOWN still says which rung decided. The document had an answer,
        the project's policy refused it, so the project is where the decision was
        made.

        The document's language here is `metadata`-sourced, NOT user-set, and
        that distinction is load-bearing: a USER-set language deliberately
        outranks the policy (a human correction is not overridden by a global
        default), so it never reaches the policy check. My first version of this
        test used a user-set language and failed — the code was right and the
        test was wrong. The next test pins that behaviour rather than leaving it
        as a thing I discovered and moved on from.
        """
        resolution = resolve_language(
            document=_document("fr", source="metadata"),
            policy=LanguagePolicy(mode="many", languages=("es", "en")),
            detect=False,
        )
        assert resolution.language is None
        assert resolution.status == "unknown"
        assert resolution.level == LEVEL_PROJECT

    def test_a_user_set_document_language_outranks_the_project_policy(self):
        """Found by a test of mine that failed for the right reason.

        A person set this document to French; the library processes Spanish and
        English. The person wins, and `level` says `document` — the global policy
        is a default, not an instruction to overwrite somebody's correction.
        """
        resolution = resolve_language(
            document=_document("fr", source="user"),
            policy=LanguagePolicy(mode="many", languages=("es", "en")),
            detect=False,
        )
        assert resolution.language == "fr"
        assert resolution.level == LEVEL_DOCUMENT


class TestUnknownAtASegmentDoesNotFallThrough:
    def test_a_segment_examined_and_undetermined_is_an_answer_not_a_gap(self):
        """`unknown-is-not-unexamined`, as control flow.

        Somebody looked at this region and could not tell. The document's
        broader answer must NOT overwrite that finding — doing so would replace
        a considered "we cannot tell" with a guess, on the one region where
        somebody actually looked.
        """
        resolution = resolve_language(
            document=_document("es"),
            segment=_segment(None, status=STATUS_UNKNOWN, source="detected"),
            policy=DOCUMENT_POLICY,
            detect=False,
        )

        assert resolution.language is None
        assert resolution.status == "unknown"
        assert resolution.level == LEVEL_SEGMENT

    def test_a_segment_that_was_never_examined_does_fall_through(self):
        """The other half of the same distinction: nothing recorded is not a
        finding, so it must fall through rather than block the cascade."""
        resolution = resolve_language(
            document=_document("es"),
            segment=_segment(),
            policy=DOCUMENT_POLICY,
            detect=False,
        )
        assert resolution.language == "es"
        assert resolution.level == LEVEL_DOCUMENT


class TestTheVocabularyIsShared:
    def test_the_levels_are_the_same_constants_language_meta_uses(self):
        """The ruling's condition: ONE vocabulary, not two spellings of
        "document" across two halves of the same cascade — a duplication that
        would be invisible in a diff."""
        from fichero_server.llm import language_policy

        assert {LEVEL_PROJECT, LEVEL_DOCUMENT, LEVEL_SEGMENT, LEVEL_READING} == {
            "project", "document", "segment", "reading"
        }
        # Every level a resolution can report is one of the four; nothing invents
        # a bare string.
        reported = {
            resolve_language(requested="fr").level,
            resolve_language(policy=LanguagePolicy(mode="one", languages=("es",)), detect=False).level,
            resolve_language(document=_document("es"), policy=DOCUMENT_POLICY, detect=False).level,
            resolve_language(
                document=_document("es"), segment=_segment("la"),
                policy=DOCUMENT_POLICY, detect=False,
            ).level,
        }
        assert reported <= {None, LEVEL_PROJECT, LEVEL_DOCUMENT, LEVEL_SEGMENT, LEVEL_READING}
        # And they are the module's own constants, so a rename moves both halves.
        assert language_policy.LEVEL_DOCUMENT is LEVEL_DOCUMENT

    def test_level_defaults_to_not_stated(self):
        assert LanguageResolution(
            language="es", status="resolved", source="user", basis="b"
        ).level is None


class TestNothingExistingChanged:
    def test_a_caller_that_passes_no_segment_resolves_exactly_as_before(self):
        """The field is additive and the rung is opt-in: 15 construction sites
        use keywords and nothing read `level` before this."""
        without = resolve_language(document=_document("es"), policy=DOCUMENT_POLICY, detect=False)
        with_none = resolve_language(
            document=_document("es"), segment=None, policy=DOCUMENT_POLICY, detect=False
        )
        assert without.language == with_none.language == "es"
        assert without.status == with_none.status
        assert without.source == with_none.source
        assert without.basis == with_none.basis


class TestScriptIsItsOwnFact:
    """Source-model slice 9 item 3 (#4938) — `source.lang.three-facts`,
    `source.lang.reading-overrides`, `source.lang.registries`.

    Script was recorded nowhere above the segment until now: `Document` had
    `language` and no `script`, so the second of the three facts had no rung to
    live on. These pin that it cascades on its own, that a reading overrides, and
    that the registry's honest codes are available instead of a guess.
    """

    def test_a_readings_own_script_wins_for_that_reading(self):
        """`reading-overrides`: a transliterated reading of a Latin-script line
        is in Arabic script, and the LINE is not. If the reading could not
        override, a transliteration would be unrecordable."""
        from fichero_server.llm.language_policy import resolve_script

        resolution = resolve_script(
            reading=SimpleNamespace(script="Arab", script_meta={"status": "known", "source": "user"}),
            segment=SimpleNamespace(script="Latn", script_meta={"status": "known", "source": "user"}),
            document=SimpleNamespace(script="Latn", script_meta=None),
        )
        assert resolution.language == "Arab"
        assert resolution.level == LEVEL_READING

    def test_it_falls_back_and_says_which_rung_answered(self):
        from fichero_server.llm.language_policy import resolve_script

        resolution = resolve_script(
            segment=SimpleNamespace(script=None, script_meta=None),
            document=SimpleNamespace(script="Latn", script_meta={"status": "known", "source": "user"}),
        )
        assert resolution.language == "Latn"
        assert resolution.level == LEVEL_DOCUMENT

    def test_nothing_recorded_anywhere_is_UNKNOWN_and_not_undetermined(self):
        """The distinction the whole behaviour protects, at the bottom of the
        cascade.

        `Zyyy` (undetermined) is a POSITIVE CLAIM that somebody looked at this
        and could not tell. "Nobody has looked" is a different state, and
        returning `Zyyy` here would collapse the two — which is exactly what
        `unknown-is-not-unexamined` forbids.
        """
        from fichero_server.llm.language_policy import SCRIPT_UNDETERMINED, resolve_script

        resolution = resolve_script()

        assert resolution.language is None
        assert resolution.language != SCRIPT_UNDETERMINED
        assert resolution.status == "unknown"
        assert resolution.source == "never_determined"
        assert resolution.level is None

    def test_a_segment_examined_and_undetermined_stops_the_walk(self):
        """Same control flow as language: somebody looked at THIS region and
        could not tell, so the document's broader answer must not overwrite that
        finding."""
        from fichero_server.llm.language_policy import resolve_script

        resolution = resolve_script(
            segment=SimpleNamespace(
                script=None, script_meta={"status": "unknown", "source": "detected"}
            ),
            document=SimpleNamespace(script="Latn", script_meta=None),
        )
        assert resolution.language is None
        assert resolution.status == "unknown"
        assert resolution.level == LEVEL_SEGMENT

    def test_language_and_script_resolve_independently(self):
        """`three-facts`. A transliterated passage shares the language and not
        the script, so the two walks must be able to answer from DIFFERENT rungs
        for the same pair of records."""
        from fichero_server.llm.language_policy import resolve_script

        document = SimpleNamespace(
            language="es", language_meta={"status": "known", "source": "user"},
            script="Latn", script_meta=None,
        )
        segment = SimpleNamespace(
            language=None, language_meta=None,
            script="Arab", script_meta={"status": "known", "source": "user"},
        )

        language = resolve_language(
            document=document, segment=segment, policy=DOCUMENT_POLICY, detect=False
        )
        script = resolve_script(segment=segment, document=document)

        assert (language.language, language.level) == ("es", LEVEL_DOCUMENT)
        assert (script.language, script.level) == ("Arab", LEVEL_SEGMENT)
        # One record pair, two facts, two different rungs — which a single
        # combined field could not express.
        assert language.level != script.level

    def test_the_registry_offers_unwritten_and_undetermined_rather_than_a_lie(self):
        """`source.lang.registries`: ISO 15924 includes the cases a "written
        scripts" list would force a lie about."""
        from fichero_server.llm.language_policy import (
            SCRIPT_UNDETERMINED,
            SCRIPT_UNWRITTEN,
            resolve_script,
        )

        # A recording has no script at all — that is `Zxxx`, not blank and not
        # Latin because the transcript happens to be typed in Latin letters.
        spoken = resolve_script(
            document=SimpleNamespace(
                script=SCRIPT_UNWRITTEN, script_meta={"status": "known", "source": "user"}
            )
        )
        assert spoken.language == SCRIPT_UNWRITTEN
        assert spoken.status == "resolved", "unwritten is a known answer, not an unknown"

        examined = resolve_script(
            document=SimpleNamespace(
                script=SCRIPT_UNDETERMINED, script_meta={"status": "known", "source": "user"}
            )
        )
        assert examined.language == SCRIPT_UNDETERMINED

    def test_a_project_can_declare_a_script_no_registry_has(self):
        """`source.lang.project-declared`, resting on ISO 15924's private-use
        range so a project's own code cannot collide with a real one."""
        from fichero_server.llm.language_policy import resolve_script, script_is_private_use

        resolution = resolve_script(
            document=SimpleNamespace(
                script="Qaaa",
                script_meta={"status": "known", "source": "user", "level": "project"},
            )
        )
        assert resolution.language == "Qaaa"
        assert script_is_private_use(resolution.language)
        assert not script_is_private_use("Latn")


class TestTwoCodesForOneLanguage:
    """Source-model slice 9 item 5 (#4938) — `source.lang.registries`.

    "language holds a BCP 47 tag and, separately, a Glottolog code (a second code
    on the engine's existing language record, not a new registry)."

    SEPARATELY is the whole instruction. BCP 47 answers "how do I tag this text
    so software handles it correctly" and is deliberately coarse; Glottolog
    answers "which language is this, as linguists individuate them" and has a
    code for languages BCP 47 cannot tag at all. A colonial document in an
    Indigenous language may be untaggable in one and precisely identified in the
    other, so collapsing them would force a choice between software correctness
    and scholarly accuracy.
    """

    def test_a_language_can_hold_both_codes_at_once(self):
        from fichero_server.llm.language_coverage import LanguageSpec

        spec = LanguageSpec(code="es", name="Spanish", glottocode="stan1288")
        assert spec.code == "es"
        assert spec.glottocode == "stan1288"

    def test_a_glottocode_without_a_useful_bcp47_tag_is_representable(self):
        """The case the separation exists for: a language Glottolog identifies
        precisely and BCP 47 can only approximate.

        `mis` is BCP 47's "uncoded languages" — a tag that says "not one of the
        ones we list". Recording that alongside an exact glottocode is strictly
        more honest than either picking a wrong neighbour tag or leaving the
        language blank.
        """
        from fichero_server.llm.language_coverage import LanguageSpec

        spec = LanguageSpec(code="mis", name="A language with no ISO 639-3 entry",
                            glottocode="abcd1234")
        assert spec.code == "mis"
        assert spec.glottocode == "abcd1234"
        # Neither field stands in for the other.
        assert spec.code != spec.glottocode

    def test_it_is_a_second_code_and_not_a_new_registry(self):
        """The instruction was explicit: a field on the EXISTING record. This
        fails if someone later introduces a parallel Glottolog record, which is
        the shape the instruction forbids."""
        from fichero_server.llm import language_coverage

        assert "glottocode" in language_coverage.LanguageSpec.model_fields
        parallel = [
            name for name in dir(language_coverage)
            if "glotto" in name.lower() and name != "LanguageSpec"
        ]
        assert parallel == [], f"a parallel Glottolog registry appeared: {parallel}"

    def test_absence_is_an_ordinary_state_not_an_incomplete_record(self):
        from fichero_server.llm.language_coverage import LanguageSpec

        assert LanguageSpec(code="es", name="Spanish").glottocode is None

    def test_a_record_written_before_this_field_still_validates(self):
        """Coverage records are persisted as JSON and read back by
        `_load_derived_record`. A payload from before this field must not become
        invalid — additive with a default is what makes that true."""
        from fichero_server.llm.language_coverage import LanguageSpec

        old_payload = {"code": "es", "name": "Spanish", "script": "Latn"}
        spec = LanguageSpec.model_validate(old_payload)
        assert spec.glottocode is None
        assert spec.script == "Latn"


def test_the_value_cascade_and_the_direction_cascade_share_one_ancestor_walk():
    """proto.value.one-resolver-with-language: a value set on a folder resolves for its page through
    the same walk the direction (and language) cascade uses."""
    from fichero_server.llm.language_policy import stated_direction_source
    from fichero_server.models import node_prototypes

    folder = SimpleNamespace(id="f", parent_id=None, direction="rtl", direction_meta={"source": "user"})
    page = SimpleNamespace(id="p", parent_id="f")
    store = {"f": folder}
    assert stated_direction_source(store.get, page) is folder
    assert node_prototypes.nearest_ancestor(page, store.get, lambda a: a.id == "f") is folder
    # a cycle ends the walk instead of looping
    a = SimpleNamespace(id="a", parent_id="b")
    b = SimpleNamespace(id="b", parent_id="a")
    assert node_prototypes.nearest_ancestor(a, {"a": a, "b": b}.get, lambda x: False) is None


class TestTheSegmentRungWalksUpItsParents:
    """`source.lang.cascade-walks-the-parent-segments` (#4938; owner 2026-11-11: a value set on the page or a region is
    "inherited by the word", and the person should see where it comes from). The segment rung asked only the segment
    itself, so a word in a Latin region of a Spanish page read Spanish."""

    @staticmethod
    def _seg(id_, kind, **facts):
        blank = {"language": None, "language_meta": None, "script": None, "script_meta": None,
                 "direction": None, "direction_meta": None}
        return SimpleNamespace(id=id_, kind=kind, **{**blank, **facts})

    def test_a_word_takes_its_regions_language_and_says_so(self):
        from fichero_server.llm.language_policy import resolve_script

        word = self._seg("w1", "word")
        line = self._seg("l1", "line")
        region = self._seg("r1", "region", language="la", script="Latn")
        page = _document("es")
        language = resolve_language(segment=word, ancestors=[line, region], document=page, policy=DOCUMENT_POLICY,
                                    detect=False)
        assert (language.language, language.level, language.segment_id) == ("la", LEVEL_SEGMENT, "r1")
        assert language.basis == "recorded on its region"
        script = resolve_script(segment=word, ancestors=[line, region])
        assert (script.language, script.segment_id, script.basis) == ("Latn", "r1", "recorded on its region")

    def test_the_nearest_parent_that_states_it_wins_and_the_segments_own_beats_them_all(self):
        line = self._seg("l1", "line", language="es")
        region = self._seg("r1", "region", language="la")
        assert resolve_language(segment=self._seg("w1", "word"), ancestors=[line, region], detect=False,
                                policy=DOCUMENT_POLICY).segment_id == "l1"
        own = self._seg("w2", "word", language="ar")
        answer = resolve_language(segment=own, ancestors=[line, region], detect=False, policy=DOCUMENT_POLICY)
        assert (answer.language, answer.segment_id, answer.basis) == ("ar", "w2", "recorded on this segment")

    def test_a_parent_examined_and_undetermined_stops_the_walk_before_the_page(self):
        region = self._seg("r1", "region", language_meta={"status": STATUS_UNKNOWN, "source": "detected"})
        answer = resolve_language(segment=self._seg("l1", "line"), ancestors=[region], document=_document("es"),
                                  policy=DOCUMENT_POLICY, detect=False)
        assert answer.status == "unknown" and answer.segment_id == "r1"
        assert answer.basis == "its region was examined and its language could not be determined"

    def test_with_no_parent_stating_anything_the_page_answers_as_before(self):
        answer = resolve_language(segment=self._seg("l1", "line"), ancestors=[self._seg("r1", "region")],
                                  document=_document("es"), policy=DOCUMENT_POLICY, detect=False)
        assert (answer.language, answer.level, answer.segment_id) == ("es", LEVEL_DOCUMENT, None)

    def test_a_direction_set_on_the_region_reaches_its_lines(self):
        from fichero_server.llm.language_policy import resolve_direction

        region = self._seg("r1", "region", direction="rtl", direction_meta={"source": "user"})
        answer = resolve_direction(segment=self._seg("l1", "line"), ancestors=[region], text="abc")
        assert (answer.language, answer.segment_id, answer.basis) == ("rtl", "r1", "recorded on its region")
