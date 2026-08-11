from enum import Enum

from fichero_server.knowledge._common import (
    enum_value,
    extract_svo,
    is_bare_is_a_copula,
    is_trivial_claim,
)
from fichero_server.models.knowledge import KnowledgeClaim


class _DemoEnum(Enum):
    person = "person"


def test_enum_value_unwraps_enums_and_preserves_plain_strings():
    assert enum_value(_DemoEnum.person) == "person"
    assert enum_value("already-plain") == "already-plain"


def test_extract_svo_strips_metadata_fields_and_defaults_missing_values():
    rich = KnowledgeClaim(
        id="claim-rich",
        text="Ada served as mayor.",
        source_document_id="doc-1",
        metadata={"verb": " served as ", "object": " mayor of Popayan "},
    )
    sparse = KnowledgeClaim(
        id="claim-sparse",
        text="No structured metadata.",
        source_document_id="doc-1",
        metadata={"verb": None},
    )

    assert extract_svo(rich) == ("served as", "mayor of Popayan")
    assert extract_svo(sparse) == ("", "")


def test_is_bare_is_a_copula_accepts_generic_type_claims():
    assert is_bare_is_a_copula("is", "a place") is True
    assert is_bare_is_a_copula("is a", "type of person", predicate_canonical="is_a") is True
    assert is_bare_is_a_copula("was", ' "kind of organization." ') is True


def test_is_bare_is_a_copula_rejects_substantive_objects():
    assert is_bare_is_a_copula("was founded in", "1851") is False
    assert is_bare_is_a_copula("is", "capital of France") is False
    assert is_bare_is_a_copula("is", "type of mining region") is False
    assert is_bare_is_a_copula("described", "a place", predicate_canonical="located_in") is False


def test_is_trivial_claim_requires_structured_subject_and_generic_copula():
    trivial = KnowledgeClaim(
        id="claim-trivial",
        text="Andagoya is a place.",
        source_document_id="doc-1",
        source_ids=["doc-1"],
        subject_canonical="Andagoya",
        predicate_verb="is",
        object_phrase="a place",
    )
    substantive = KnowledgeClaim(
        id="claim-substantive",
        text="Andagoya was founded in 1851.",
        source_document_id="doc-1",
        source_ids=["doc-1"],
        subject_canonical="Andagoya",
        predicate_verb="was founded in",
        object_phrase="1851",
    )

    assert is_trivial_claim(trivial) is True
    assert is_trivial_claim(substantive) is False


def test_is_trivial_claim_falls_back_to_metadata_subject_verb_and_object():
    claim = KnowledgeClaim(
        id="claim-meta",
        text="Andagoya is a place.",
        source_document_id="doc-1",
        metadata={"subject": "Andagoya", "verb": "is", "object": "a place"},
    )

    assert is_trivial_claim(claim) is True


def test_is_trivial_claim_rejects_blank_subject_even_with_generic_object():
    claim = KnowledgeClaim(
        id="claim-no-subject",
        text="Is a place.",
        source_document_id="doc-1",
        metadata={"subject": "   ", "verb": "is", "object": "a place"},
    )

    assert is_trivial_claim(claim) is False
