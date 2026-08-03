"""Language policy resolution (#2092).

The behaviour under test is not "does it pick a language" — it is "does it
refuse to pick one when it has no grounds". A resolver that always answers is
exactly the failure this issue exists to fix: on Spanish colonial material an
unjustified "English" produces fluent, plausible, wrong output.
"""

from __future__ import annotations

import pytest

from fichero_server.llm.language_policy import (
    NEVER_DETERMINED,
    RESOLVED,
    SOURCE_DETECTED,
    SOURCE_USER,
    STATUS_KNOWN,
    STATUS_UNKNOWN,
    UNKNOWN,
    UNKNOWN_LANGUAGE_INSTRUCTION,
    LanguagePolicy,
    UnknownDocumentLanguage,
    apply_detected_language,
    build_language_meta,
    describe,
    is_user_set,
    parse_policy,
    prompt_language,
    read_document_language,
    require_language,
    resolve_language,
    set_user_language,
)

SPANISH = (
    "El gobernador de la provincia dio cuenta de que los vecinos de la villa "
    "no han pagado los tributos que se les pidieron por el año pasado, y que "
    "por esta razon se les ha de apremiar con la pena que se ha señalado."
)
ENGLISH = (
    "The governor of the province reported that the inhabitants of the town "
    "have not paid the tributes that were asked of them for the past year, "
    "and that for this reason they are to be compelled with the stated penalty."
)


def _doc(**kwargs):
    """A document stand-in. The resolver reads dicts and models alike."""
    return {"id": "doc-1", "language": None, "language_meta": None, **kwargs}


# ---------------------------------------------------------------------------
# Parsing the three modes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,mode,languages",
    [
        (None, "unset", ()),
        ("", "unset", ()),
        ("   ", "unset", ()),
        ("Spanish", "one", ("Spanish",)),
        ("Spanish, English", "many", ("Spanish", "English")),
        ("Spanish,English,Latin", "many", ("Spanish", "English", "Latin")),
        ("document", "document", ()),
        ("Language of the document", "document", ()),
    ],
)
def test_parse_policy_covers_the_three_modes(raw, mode, languages):
    policy = parse_policy(raw)
    assert policy.mode == mode
    assert policy.languages == languages


def test_existing_single_language_setting_keeps_its_meaning():
    """Back-compat: libraries already holding one language name must not shift."""
    assert parse_policy("Spanish") == LanguagePolicy(mode="one", languages=("Spanish",))


# ---------------------------------------------------------------------------
# Mode 1 — one language, forced
# ---------------------------------------------------------------------------


def test_one_language_mode_forces_it_over_the_text():
    policy = parse_policy("Spanish")
    resolution = resolve_language(document=_doc(), text=ENGLISH, policy=policy)
    assert resolution.language == "Spanish"
    assert resolution.status == RESOLVED
    assert resolution.source == "policy"


def test_one_language_mode_needs_no_text():
    policy = parse_policy("Spanish")
    assert resolve_language(text="", policy=policy).language == "Spanish"


# ---------------------------------------------------------------------------
# Mode 2 — several languages
# ---------------------------------------------------------------------------


def test_many_mode_picks_the_detected_language_from_the_set():
    policy = parse_policy("Spanish, English")
    assert resolve_language(document=_doc(), text=SPANISH, policy=policy).language == "Spanish"
    assert resolve_language(document=_doc(), text=ENGLISH, policy=policy).language == "English"


def test_many_mode_prefers_the_documents_own_recorded_language():
    policy = parse_policy("Spanish, English")
    doc = _doc(
        language="Spanish",
        language_meta=build_language_meta(status=STATUS_KNOWN, source=SOURCE_DETECTED),
    )
    resolution = resolve_language(document=doc, text=ENGLISH, policy=policy)
    assert resolution.language == "Spanish"


def test_many_mode_refuses_a_language_outside_the_set():
    """Never fall back to the first listed language.

    Choosing Spanish for a French document because Spanish was listed first is
    the confident-nonsense failure in miniature.
    """
    policy = parse_policy("Spanish, English")
    doc = _doc(
        language="French",
        language_meta=build_language_meta(status=STATUS_KNOWN, source=SOURCE_DETECTED),
    )
    resolution = resolve_language(document=doc, text="", policy=policy)
    assert resolution.language is None
    assert resolution.status == UNKNOWN
    assert "French" in resolution.basis
    assert "Spanish" not in resolution.basis.split("(")[0]


# ---------------------------------------------------------------------------
# Mode 3 — language of the document
# ---------------------------------------------------------------------------


def test_document_mode_carries_the_recorded_language():
    policy = parse_policy("document")
    doc = _doc(
        language="Spanish",
        language_meta=build_language_meta(status=STATUS_KNOWN, source=SOURCE_DETECTED),
    )
    assert resolve_language(document=doc, text="", policy=policy).language == "Spanish"


def test_document_mode_detects_when_nothing_is_recorded():
    policy = parse_policy("document")
    assert resolve_language(document=_doc(), text=SPANISH, policy=policy).language == "Spanish"


def test_document_mode_does_not_substitute_the_global_default():
    """"Language of the document" must not silently answer with the library default.

    The user asked what THIS document is in. Answering with a library-wide
    setting answers a different question, and does it invisibly.
    """
    policy = parse_policy("document")
    resolution = resolve_language(document=_doc(), text="", policy=policy)
    assert resolution.language is None
    assert resolution.status == UNKNOWN


# ---------------------------------------------------------------------------
# Per-document override beats the global default
# ---------------------------------------------------------------------------


def test_user_set_document_language_beats_the_global_default():
    policy = parse_policy("English")
    doc = _doc()
    set_user_language(doc, "Spanish")
    resolution = resolve_language(document=doc, text=ENGLISH, policy=policy)
    assert resolution.language == "Spanish"
    assert resolution.source == SOURCE_USER
    assert "user" in resolution.basis


def test_an_explicit_node_request_beats_everything():
    policy = parse_policy("English")
    doc = _doc()
    set_user_language(doc, "Spanish")
    resolution = resolve_language(requested="Latin", document=doc, text="", policy=policy)
    assert resolution.language == "Latin"
    assert resolution.source == "requested"


@pytest.mark.parametrize("requested", ["", "auto", "AUTO", None, "  "])
def test_auto_and_empty_are_not_treated_as_a_language(requested):
    """The bug this fixes: "auto" reaching the prompt as a literal language."""
    policy = parse_policy("Spanish")
    assert resolve_language(requested=requested, text="", policy=policy).language == "Spanish"


# ---------------------------------------------------------------------------
# Unknown stays unknown, and stays visible
# ---------------------------------------------------------------------------


def test_unknown_is_never_silently_english():
    policy = parse_policy("Spanish, English")
    resolution = resolve_language(document=_doc(), text="", policy=policy)
    assert resolution.language is None
    assert resolution.status == UNKNOWN
    assert resolution.basis  # a reason a user can read


def test_unknown_is_visible_in_the_reported_payload():
    policy = parse_policy("document")
    payload = describe(resolve_language(document=_doc(), text="", policy=policy))
    assert payload["language"] is None
    assert payload["language_status"] == UNKNOWN
    assert payload["language_basis"]


def test_unknown_prompts_follow_the_source_instead_of_asserting_english():
    policy = parse_policy("document")
    resolution = resolve_language(document=_doc(), text="", policy=policy)
    assert prompt_language(resolution) == UNKNOWN_LANGUAGE_INSTRUCTION
    assert "English" not in prompt_language(resolution)


def test_require_language_raises_rather_than_guessing():
    policy = parse_policy("document")
    resolution = resolve_language(document=_doc(), text="", policy=policy)
    with pytest.raises(UnknownDocumentLanguage):
        require_language(resolution)


def test_never_determined_is_distinguishable_from_examined_and_unknown():
    """Two different facts that need opposite responses from a user.

    "nothing has looked" means run detection; "detection ran and could not
    tell" means this document needs a person. A single null cannot say both.
    """
    never = read_document_language(_doc())
    assert never.source == NEVER_DETERMINED

    examined = read_document_language(
        _doc(language_meta=build_language_meta(status=STATUS_UNKNOWN, source=SOURCE_DETECTED))
    )
    assert examined.status == UNKNOWN
    assert examined.source == SOURCE_DETECTED
    assert never.basis != examined.basis


def test_unset_policy_preserves_the_legacy_english_fallback():
    """Libraries that never set a policy must not shift under this change."""
    resolution = resolve_language(document=_doc(), text="", policy=parse_policy(""))
    assert resolution.language == "English"
    assert resolution.status == RESOLVED
    assert resolve_language(text=SPANISH, policy=parse_policy("")).language == "Spanish"


# ---------------------------------------------------------------------------
# A user's correction survives re-extraction
# ---------------------------------------------------------------------------


def test_user_set_language_survives_re_extraction():
    doc = _doc()
    set_user_language(doc, "Spanish")
    assert is_user_set(doc)

    outcome = apply_detected_language(doc, "English", confidence=0.99)

    assert outcome.applied is False
    assert doc["language"] == "Spanish"
    assert doc["language_meta"]["source"] == SOURCE_USER


def test_re_extraction_disagreeing_with_a_user_reports_the_conflict():
    """Surfaced, not resolved. A disagreement a user cannot see is one they
    cannot correct — the same rule date_extract applies to user-pinned dates."""
    doc = _doc()
    set_user_language(doc, "Spanish")
    outcome = apply_detected_language(doc, "English")
    assert outcome.conflict == {"user_language": "Spanish", "detected_language": "English"}


def test_re_extraction_agreeing_with_a_user_reports_no_conflict():
    doc = _doc()
    set_user_language(doc, "Spanish")
    assert apply_detected_language(doc, "Spanish").conflict is None


def test_a_users_undeterminable_assertion_also_survives():
    """"I looked and I cannot tell" is itself a finding worth protecting."""
    doc = _doc()
    set_user_language(doc, None)
    apply_detected_language(doc, "English")
    assert doc["language"] is None
    assert doc["language_meta"]["source"] == SOURCE_USER


def test_detection_overwrites_a_previous_detection():
    doc = _doc()
    assert apply_detected_language(doc, "English").applied is True
    assert apply_detected_language(doc, "Spanish").applied is True
    assert doc["language"] == "Spanish"


def test_detection_with_no_answer_records_examined_not_english():
    doc = _doc()
    apply_detected_language(doc, None)
    assert doc["language"] is None
    assert doc["language_meta"]["status"] == STATUS_UNKNOWN
    assert doc["language_meta"]["source"] == SOURCE_DETECTED
