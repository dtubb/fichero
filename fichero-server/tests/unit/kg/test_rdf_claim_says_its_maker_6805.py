"""A claim's RDF statement says what made it, whether a person reviewed it (#6805)."""

from rdflib import Literal

from fichero_server.knowledge import triples
from fichero_server.models.knowledge import (
    AttributionRole,
    AttributionStep,
    ClaimCurationState,
    KnowledgeClaim,
)


def test_a_claim_names_provider_model_person_and_review_state():
    claim = KnowledgeClaim(
        id="c1", text="Pedro signed.", source_document_id="d1", provider="ollama", model="llama3",
        curation_state=ClaimCurationState.curated,
        attribution_chain=[AttributionStep(role=AttributionRole.editor, name="Ana")],
    )
    graph = triples.make_graph()
    triples.claim_to_triples(graph, claim)
    uri = triples._claim_uri("c1")
    assert (uri, triples.FICHERO.provider, Literal("ollama")) in graph
    assert (uri, triples.FICHERO.model, Literal("llama3")) in graph
    assert (uri, triples.FICHERO.madeByPerson, Literal("Ana")) in graph
    assert (uri, triples.FICHERO.curationState, Literal("curated")) in graph
