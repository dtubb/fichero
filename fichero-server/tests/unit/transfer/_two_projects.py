"""Two open projects on one engine, and a folder in the source worth transferring (#5657).

The target is the `client` fixture's library (`test.fichero`, the library header); the source is a
second package opened beside it, as a person with two projects open has. The folder holds two pages
with everything that must travel with a page, plus edges to a page that stays behind.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fichero_server.api.main  # noqa: F401  (registers every action and route)
from fichero_server.api.main import get_library_database_for_write
from fichero_server.db.manager import db_manager
from fichero_server.knowledge.authorities import link_entity
from fichero_server.models import (
    Artifact,
    ContentRepresentation,
    DocType,
    Document,
    FileType,
    ReadingChoice,
)
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.canvas import CanvasItem, CanvasItemKind, CanvasLayout
from fichero_server.models.hands import Hand, HandAttribution
from fichero_server.models.knowledge import (
    Annotation,
    ClassificationDimension,
    ClassificationValue,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    ProvenanceKind,
)
from fichero_server.models.readings import LibraryReadingLevel
from fichero_server.models.transfer import TransferRecord
from fichero_server.models.typed_links import TypedLink
from PIL import Image

WIKIDATA = "Q4115189"


def png(path: Path, color: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color).save(path, format="PNG")
    return path


def open_source(tmp_path: Path, name: str = "Origen.fichero") -> Path:
    package = tmp_path / name
    for sub in ("lance", "storage", "files"):
        (package / sub).mkdir(parents=True, exist_ok=True)
    db_manager.get_database(package)
    return package


def header_decides(app) -> None:
    """The library header picks the target, as in the app (the fixture pins it to `test.fichero` otherwise)."""
    app.dependency_overrides.pop(get_library_database_for_write, None)


def _segment(db, page, pass_id, rect, kind="line", parent=None):
    from fichero_server.models import Segment
    from fichero_server.models.segments import bbox_and_tile_from_anchor

    anchor = SourceAnchor(document_id=page.id, rect=rect)
    x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
    seg = Segment(document_id=page.id, pass_id=pass_id, kind=kind, anchor=anchor, parent_segment_id=parent,
                  bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h, tile=tile, doc_kind=f"{page.id}:{kind}",
                  provenance_kind=ProvenanceKind.human, created_by="maker")
    db.save(seg)
    return seg


@dataclass
class Box:
    folder: Document
    page1: Document
    page2: Document
    elsewhere: Document
    line: object
    word: object
    entity: KnowledgeEntity
    claim: KnowledgeClaim
    target_entity: KnowledgeEntity
    linked_original: Path


def build_box(source, target, tmp_path: Path) -> Box:
    """A folder of two pages in the source, and a person already in the target's graph."""
    from fichero_server.models import SegmentPass

    source_package = Path(source.path).parent
    shelf = Document(name="Shelf", doc_type=DocType.folder)
    folder = Document(name="Box 1", doc_type=DocType.folder)
    elsewhere = Document(name="Elsewhere", parent_id=shelf.id, doc_type=DocType.file)
    page1 = Document(name="p1.png", parent_id=folder.id, doc_type=DocType.file, file_type=FileType.image,
                     path=str(png(source_package / "files" / "p1.png", "red")), prototype_key="carta")
    linked = png(tmp_path / "outside" / "p2.png", "blue")
    page2 = Document(name="p2.png", parent_id=folder.id, doc_type=DocType.file, file_type=FileType.image,
                     path=str(linked), sort_order=1)
    # In the folder too: a page in the Trash (stays), an alias to a page that travels (rewritten) and
    # an alias to the page left behind (would dangle: stays, listed).
    trashed = Document(name="torn.png", parent_id=folder.id, doc_type=DocType.file, deleted_by="maker")
    alias_in = Document(name="p1 alias", parent_id=folder.id, node_kind="alias", alias_target_id=page1.id)
    alias_out = Document(name="elsewhere alias", parent_id=folder.id, node_kind="alias", alias_target_id=elsewhere.id)
    for doc in (shelf, folder, elsewhere, page1, page2, alias_in, alias_out):
        source.save(doc)
    from fichero_server.core.timeutil import utc_now

    source.save(trashed.model_copy(update={"deleted_at": utc_now()}))
    source.save(ClassificationValue(dimension=ClassificationDimension.document_prototype, key="carta", label="Carta"))

    pass_row = SegmentPass(document_id=page1.id, name="mine", provenance_kind=ProvenanceKind.human)
    source.save(pass_row)
    line = _segment(source, page1, pass_row.id, [0.1, 0.1, 0.8, 0.1])
    word = _segment(source, page1, pass_row.id, [0.1, 0.1, 0.2, 0.1], kind="word", parent=line.id)
    # Readings at two edition levels on the line, and the word read at a level only the source declares.
    source.save(LibraryReadingLevel(key="diplomatic", label="Diplomatic"))
    expanded = ContentRepresentation(document_id=page1.id, segment_id=line.id, kind="transcription", level="expanded",
                                     content="Juan de la Cruz vende", source_anchor=SourceAnchor(document_id=page1.id, segment_id=line.id),
                                     provenance_kind=ProvenanceKind.human, created_by="maker")
    source.save(expanded)
    line_reading = ContentRepresentation(document_id=page1.id, segment_id=line.id, kind="transcription", level="as_written",
                                         content="Juan de la Cruz vende", source_anchor=SourceAnchor(document_id=page1.id, segment_id=line.id),
                                         provenance_kind=ProvenanceKind.human, created_by="maker")
    word_reading = ContentRepresentation(document_id=page1.id, segment_id=word.id, kind="transcription", level="diplomatic",
                                         content="Juan", source_anchor=SourceAnchor(document_id=page1.id, segment_id=word.id),
                                         provenance_kind=ProvenanceKind.human, created_by="maker")
    source.save(line_reading)
    source.save(word_reading)
    source.save(ReadingChoice(document_id=page1.id, segment_id=line.id, kind="transcription", representation_id=line_reading.id, chosen_by="maker"))
    source.save(Artifact(document_id=page1.id, artifact_type="ocr", content="Juan de la Cruz vende"))
    hand = Hand(label="Hand A", scribe="Escribano", provenance_kind=ProvenanceKind.human)
    source.save(hand)
    source.save(HandAttribution(hand_id=hand.id, segment_id=line.id, provenance_kind=ProvenanceKind.human, created_by="maker"))
    source.save(Annotation(kind="highlight", document_id=page1.id, text="look"))
    # The folder's canvas: a link between the two pages travels; one to the page left behind is cut.
    source.save(CanvasLayout(id=f"{folder.id}::{page1.id}", folder_id=folder.id, item_id=page1.id, x=10, y=20))
    source.save(CanvasItem(folder_id=folder.id, kind=CanvasItemKind.link, source_item_id=page1.id, target_item_id=page2.id))
    source.save(CanvasItem(folder_id=folder.id, kind=CanvasItemKind.link, source_item_id=page1.id, target_item_id=elsewhere.id))

    entity = KnowledgeEntity(canonical_name="Juan de la Cruz", entity_type=EntityType.person, curation_state="verified")
    source.save(entity)
    link_entity(source, entity.id, "wikidata", WIKIDATA, provenance_kind=ProvenanceKind.human, created_by="maker")
    source.save(TypedLink(from_kind="segment", from_id=word.id, to_kind="entity", to_id=entity.id, link_type="names",
                          provenance_kind=ProvenanceKind.human, created_by="maker"))
    claim = KnowledgeClaim(text="Juan de la Cruz sells a house", source_document_id=page1.id,
                           source_ids=[page1.id, elsewhere.id], subject_entity_id=entity.id, entity_ids=[entity.id],
                           curation_state="curated", created_by="maker", provenance_kind=ProvenanceKind.human)
    source.save(claim)
    # A link from a moved page to the page that stays: cut and listed.
    source.save(TypedLink(from_kind="document", from_id=page2.id, to_kind="document", to_id=elsewhere.id,
                          link_type="glosses", provenance_kind=ProvenanceKind.human))

    # The target already knows this person, by the same Wikidata id, under another spelling.
    target_entity = KnowledgeEntity(canonical_name="J. de la Cruz", entity_type=EntityType.person)
    target.save(target_entity)
    link_entity(target, target_entity.id, "wikidata", WIKIDATA, provenance_kind=ProvenanceKind.human, created_by="other")
    # Same key, different fields: the target's reading level `as_written` keeps its own label.
    [as_written] = target.query(LibraryReadingLevel, key="as_written")
    target.save(as_written.model_copy(update={"label": "Como se escribe"}))
    return Box(folder, page1, page2, elsewhere, line, word, entity, claim, target_entity, linked)


def table_counts(db) -> dict[str, int]:
    """Rows per persisted model, the transfer's own record left out."""
    return {model.__name__: len(db.all(model)) for model in db._all_schema_models() if model is not TransferRecord}
