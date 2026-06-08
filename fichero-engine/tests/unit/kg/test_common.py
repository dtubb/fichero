from fichero.kg._common import is_bare_is_a_copula, is_trivial_claim
from fichero.knowledge_models import KnowledgeClaim


def test_is_bare_is_a_copula_accepts_generic_type_claims():
    assert is_bare_is_a_copula("is", "a place") is True
    assert is_bare_is_a_copula("is a", "type of person", predicate_canonical="is_a") is True


def test_is_bare_is_a_copula_rejects_substantive_objects():
    assert is_bare_is_a_copula("was founded in", "1851") is False
    assert is_bare_is_a_copula("is", "capital of France") is False


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
