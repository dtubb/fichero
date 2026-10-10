"""Officials are not parties (ruled 2026-10-10, `finding-documents.md`): a judge or notary who signs most of a
folder's documents links none of them into a case; two documents that share their own parties still group."""

from __future__ import annotations

from fichero_server.finddocs.propose import _groups
from fichero_server.models.found_documents import ProposedDocument


def _doc(i: int, *parties: str) -> ProposedDocument:
    return ProposedDocument(index=i, name=f"d{i}", page_ids=[f"p{i}"], first_position=i, last_position=i,
                            parties=list(parties), confidence=0.9)


def test_a_judge_and_secretary_on_every_document_link_nothing() -> None:
    officials = ("Juez Pedro Arango", "Secretario Luis Mena")
    documents = [_doc(0, *officials, "Ana Rosa Palacios", "Juan Mosquera"),
                 _doc(1, *officials, "Ana Rosa Palacios", "Juan Mosquera"),
                 _doc(2, *officials, "Carlos Rentería", "Mina Andágueda"),
                 _doc(3, *officials, "Tomás Valencia", "Elena Cuesta")]
    groups = _groups(documents)
    assert [g.document_indexes for g in groups] == [[0, 1]]
    assert set(groups[0].parties) == {"Ana Rosa Palacios", "Juan Mosquera"}


def test_two_documents_sharing_two_names_still_group() -> None:
    """Below four documents nobody is an official: two people on both of two documents are its parties."""
    groups = _groups([_doc(0, "Ana Rosa Palacios", "Juan Mosquera"), _doc(1, "Ana Rosa Palacios", "Juan Mosquera")])
    assert [g.document_indexes for g in groups] == [[0, 1]]
