"""An imported pass says it came from a file, names what the file says made it, and ranks as an
import (#5150).

WHY: `format.import` stamped every imported pass `human`. A Transkribus PAGE file is often
ABBYY's or an HTR model's output; calling it a person's work is the "machine claims stored as
human" class (#4868/#4869), and it put every import in the hand-curated tier of the pass ladder
(#5146), above a person's own work in waiting. If this regresses, an import reads as a person's
again, or the file's own statement of who made it is lost, or an import outranks -- or is
outranked by -- the wrong tier.

The file's statement is read with plain lxml, never with the engine's readers.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.core.timeutil import utc_now
from fichero_server.models import ContentRepresentation, DocType, Document, FileType, Status
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import Segment, SegmentPass

CORPUS = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus"
TRANSKRIBUS = CORPUS / "transkribus_german-fraktur_nzz-17840710.page.xml"
GENJI = CORPUS / "digitalgenji_japanese-vertical_kouigenji-01.tei.xml"
PERSON = ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _doc(db) -> Document:
    doc = Document(name="p.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/p/p.jpg", status=Status.completed)
    db.save(doc)
    return doc


def _import(db, doc, path: Path) -> SegmentPass:
    result = registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(path)}, PERSON)
    return db.get(SegmentPass, result.result["pass_id"])


def _transkribus_maker_by_lxml() -> str:
    """The Comments' `Producer:` (Creator is empty in this file) and the TranskribusMetadata
    comment's docId and status."""
    import re

    root = etree.parse(str(TRANSKRIBUS)).getroot()
    metadata = next(el for el in root.iter() if isinstance(el.tag, str) and etree.QName(el).localname == "Metadata")
    comments = next(el for el in metadata if isinstance(el.tag, str) and etree.QName(el).localname == "Comments")
    producer = next(line.split(":", 1)[1].strip() for line in comments.text.splitlines()
                    if line.strip().startswith("Producer:"))
    note = next(el.text for el in metadata.iter() if not isinstance(el.tag, str) and "TranskribusMetadata" in el.text)
    doc_id = re.search(r'docId="([^"]*)"', note).group(1)
    status = re.search(r'status="([^"]*)"', note).group(1)
    return f"{producer}; Transkribus (docId {doc_id}, status {status})"


def test_a_transkribus_page_is_the_files_and_names_its_maker(db):
    pass_row = _import(db, _doc(db), TRANSKRIBUS)
    assert pass_row.provenance_kind == ProvenanceKind.external_import
    assert pass_row.actor == "historian", "who brought it"
    assert pass_row.provider == _transkribus_maker_by_lxml(), "what the file says made it"

    segments = [s for s in db.all(Segment) if s.pass_id == pass_row.id]
    readings = [r for r in db.all(ContentRepresentation) if r.segment_id in {s.id for s in segments}]
    assert segments and readings
    assert {s.provenance_kind for s in segments} == {ProvenanceKind.external_import}
    assert {r.provenance_kind for r in readings} == {ProvenanceKind.external_import}


def test_a_tei_edition_names_its_responsibilities(db):
    root = etree.parse(str(GENJI)).getroot()
    tei = "{http://www.tei-c.org/ns/1.0}"
    names = [n.text for stmt in root.iter(f"{tei}respStmt") for n in stmt if n.tag == f"{tei}name"]
    provider = _import(db, _doc(db), GENJI).provider
    assert names and all(name in provider for name in names), provider


def test_it_ranks_as_an_import_above_a_machine_and_below_a_person(db):
    doc = _doc(db)
    imported = _import(db, doc, TRANSKRIBUS)
    later = utc_now() + timedelta(hours=1)

    machine = SegmentPass(document_id=doc.id, name="kraken run", provenance_kind=ProvenanceKind.workflow,
                          created_at=later)
    db.save(machine)
    answer = document_text(db, doc.id)
    assert (answer.pass_id, answer.pass_basis) == (imported.id, "imported"), "a newer machine run does not win"

    person = SegmentPass(document_id=doc.id, name="my pass", provenance_kind=ProvenanceKind.human,
                         created_at=imported.created_at - timedelta(hours=1))
    db.save(person)
    answer = document_text(db, doc.id)
    assert (answer.pass_id, answer.pass_basis) == (person.id, "human-touched"), "a person's pass wins"
