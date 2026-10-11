"""How a row JOINS the set a transfer carries (#5657).

`id_map_classification.py` says what a transfer does with every id field; this says which of those
MAPPED fields bring a row along. It names no id field of its own: every field below must be a
`MAPPED` key of the classification (pinned by `tests/unit/transfer/test_transfer_a_page_whole.py`), so the
two cannot drift into a second list.

- ``owners`` — a row travels when ANY of these names something in the set (a segment by its page,
  a reading by its segment, a claim by the page it rests on).
- ``whole`` — every non-empty value of these must be in the set too, or the row does not travel: it
  is cut and listed (a link with one end left behind, a canvas link item, a reading-order entry
  pointing at a segment that stays). Any other MAPPED field naming something outside the set is cut
  from a row that still travels (a note's link list, a claim's second source).

A model with ``whole`` and no ``owners`` is an EDGE: found from either end, carried only with both.
`KnowledgeEntity` joins differently — by being NAMED (see ``ENTITY_REFERENCES``) — and `Document`
by the subtree walk.
"""

from __future__ import annotations

from dataclasses import dataclass

from fichero_server.transfer.id_map_classification import CLASSIFICATION, MAPPED


@dataclass(frozen=True)
class Join:
    owners: tuple[str, ...] = ()
    whole: tuple[str, ...] = ()


JOINS: dict[str, Join] = {
    # the node's own records
    "Artifact": Join(owners=("document_id",)),
    "Rendition": Join(owners=("document_id",)),
    "ConvertedBoxOrigin": Join(owners=("document_id",)),
    "DocumentNote": Join(owners=("document_id",)),
    "ImageEditChain": Join(owners=("document_id",)),
    "RightsRecord": Join(owners=("target_id",)),
    "BookStructureNode": Join(owners=("source_document_id",)),
    "ReferenceProvenance": Join(owners=("document_id",)),
    # passes and lines
    "SegmentPass": Join(owners=("document_id",)),
    "Segment": Join(owners=("document_id",)),
    "SegmentPassChoice": Join(owners=("document_id",), whole=("pass_id",)),
    "SegmentMatch": Join(owners=("document_id",), whole=("from_segment_id", "to_segment_id")),
    "SegmentCarry": Join(whole=("original_id", "copy_id")),
    "SegmentForwarding": Join(owners=("document_id",)),
    "SegmentVersion": Join(owners=("document_id",)),
    "PageLineMap": Join(owners=("id",)),
    # readings
    "ContentRepresentation": Join(owners=("document_id",)),
    "ContentRepresentationRevision": Join(owners=("representation_id",)),
    "ReadingChoice": Join(owners=("document_id",), whole=("representation_id",)),
    "ReadingOrder": Join(owners=("document_id",)),
    "ReadingOrderEntry": Join(owners=("order_id",), whole=("segment_id",)),
    "EditorialFact": Join(owners=("segment_id", "representation_id")),
    "Campaign": Join(owners=("document_id",)),
    "CampaignMembership": Join(owners=("campaign_id",), whole=("segment_id",)),
    "ReadingCampaigns": Join(owners=("representation_id",)),
    # palaeography
    "HandAttribution": Join(owners=("segment_id",)),
    "LetterformDescription": Join(owners=("segment_id",)),
    # marks and notes
    "Annotation": Join(owners=("document_id", "page_id", "folder_id")),
    "Note": Join(owners=("page_id", "folder_id")),
    "CheckVerdict": Join(owners=("document_id",)),
    # canvases
    "CanvasLayout": Join(owners=("folder_id",), whole=("item_id",)),
    "CanvasItem": Join(owners=("folder_id",), whole=("source_item_id", "target_item_id")),
    "SpatialNode": Join(owners=("room_id",), whole=("source_id",)),
    "SpatialConnection": Join(owners=("room_id",), whole=("source_node_id", "target_node_id")),
    # knowledge
    "KnowledgeClaim": Join(owners=("source_document_id", "source_ids")),
    "EntityMergeAudit": Join(owners=("target_entity_id",)),
    "ClaimMergeAudit": Join(owners=("target_claim_id",)),
    "EntityMatchCandidate": Join(whole=("survivor_entity_id", "candidate_entity_id")),
    "Interpretation": Join(owners=("document_id", "claim_id"), whole=("document_id", "claim_id")),
    # edges: carried only with both ends
    "TypedLink": Join(whole=("from_id", "to_id")),
    "NoteLink": Join(whole=("source_note_id", "target_note_id")),
    "KnowledgeClaimLink": Join(whole=("claim_id", "related_claim_id")),
    "DocumentCitation": Join(whole=("source_document_id", "target_document_id")),
    "LibraryItemLink": Join(whole=("source_id", "target_id")),
}

#: A link end that names something outside any project (an authority's URI) is not an id at all:
#: `(field, kind field, external kind)`. A `same_as` link from a carried entity to Wikidata travels.
EXTERNAL_ENDS: dict[str, tuple[str, str]] = {
    "TypedLink.from_id": ("from_kind", "uri"),
    "TypedLink.to_id": ("to_kind", "uri"),
}

#: The fields that make an entity travel: the claims resting on moved pages name it, or a moved row
#: links to it (a segment that `names` a place). `transfer.entities.*`.
ENTITY_REFERENCES: tuple[str, ...] = (
    "KnowledgeClaim.subject_entity_id",
    "KnowledgeClaim.entity_ids",
    "KnowledgeClaim.speaker_entity_id",
    "KnowledgeClaim.subject_of_inquiry_entity_id",
    "KnowledgeClaim.scribe_entity_id",
    "KnowledgeClaim.editor_entity_id",
)
#: A typed link end of this kind names an entity (`TypedLink.to_kind == "entity"`).
ENTITY_LINK_KIND = "entity"


def join_fields() -> list[str]:
    """Every classification key this module names (for the pin that they are all MAPPED)."""
    keys = [f"{model}.{name}" for model, join in JOINS.items() for name in (*join.owners, *join.whole)]
    return sorted({*keys, *EXTERNAL_ENDS, *ENTITY_REFERENCES})


def unmapped_join_fields() -> list[str]:
    return [key for key in join_fields() if CLASSIFICATION.get(key, ("", ""))[0] != MAPPED]
