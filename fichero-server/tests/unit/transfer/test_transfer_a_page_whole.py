"""A folder copied into another project arrives whole, with every id re-pointed (#5657, build order 3).

WHY: a page is not its row. Its pictures, passes and lines, every reading, its artifacts, the hands
that wrote it, its marks, its canvas and the people named on it are records a person made; a copy
that drops one, or writes one still pointing at the source's ids, loses work or leaves ids that name
nothing. Through the real route, between two real open projects, this pins:

- `transfer.page.*`: every kind lands, with consistent new ids (`test_a_copied_folder_arrives_whole`);
- `transfer.cut.listed-never-silent`: an edge to the page left behind is cut and listed, never written;
- `transfer.entities.*`: the person matched by Wikidata id is PROPOSED, not merged; marks kept;
- no id in any carried row names a row the target lacks (`test_no_carried_row_names_a_missing_row`);
- `transfer.action.dry-run`: the plan writes nothing in either project and says the same;
- `transfer.action.undo-copy`: undo sends the copy to the target's Trash and withdraws the proposals;
- the join table names only MAPPED ids of the classification (no second list of id fields).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fichero_server.api.main import app
from fichero_server.db.manager import db_manager
from fichero_server.models import Artifact, ContentRepresentation, Document, ReadingChoice, Segment, SegmentPass
from fichero_server.models.canvas import CanvasItem, CanvasLayout
from fichero_server.models.hands import Hand, HandAttribution
from fichero_server.models.knowledge import (
    Annotation,
    ClassificationValue,
    EntityMatchCandidate,
    KnowledgeClaim,
    KnowledgeEntity,
    PendingMatchMethod,
    PendingMatchState,
)
from fichero_server.models.readings import LibraryReadingLevel
from fichero_server.models.transfer import TransferRecord
from fichero_server.models.typed_links import TypedLink
from fichero_server.transfer import membership
from fichero_server.transfer.copy import _mapped_values
from tests.unit.transfer._two_projects import build_box, header_decides, open_source, table_counts


def _copy(client, source_package, items, **extra):
    return client.post("/api/documents/transfer", json={"items": items, "source": str(source_package), **extra})


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_the_join_table_names_only_mapped_ids():
    """WHY: which rows come along is declared beside the id map, not as a second list of id fields."""
    assert membership.unmapped_join_fields() == []


def test_a_copied_folder_arrives_whole(client, db, tmp_path):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    source_before = table_counts(source)

    response = _copy(client, source_package, [box.folder.id])
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["state"] == "done" and not result["dry_run"]
    [folder_id] = result["copies"]

    # The node and its pages, under the target's Sources folder, each saying where it came from.
    folder = db.get(Document, folder_id)
    sources_folder = db.get(Document, folder.parent_id)
    assert folder.name == "Box 1" and sources_folder.name == "Sources"
    pages = {d.name: d for d in db.query(Document, parent_id=folder_id)}
    assert set(pages) == {"p1.png", "p2.png"}
    page1, page2 = pages["p1.png"], pages["p2.png"]
    assert page1.id != box.page1.id
    assert page1.metadata["transferred_from"]["node"] == box.page1.id
    assert page1.metadata["transferred_from"]["transfer"] == result["transfer_id"]

    # The in-package original is copied byte for byte into the target; the linked one stays a reference.
    assert Path(page1.path).is_relative_to(Path(db.path).parent / "files")
    assert _sha(page1.path) == _sha(box.page1.path)
    assert page2.path == str(box.linked_original)
    assert result["linked_files"] == [box.page2.id] and result["files"] == 1

    # The kind travels by key, made in the target with its label (it had none).
    assert page1.prototype_key == "carta"
    assert [v.label for v in db.query(ClassificationValue, key="carta")] == ["Carta"]

    # Passes, lines, readings at two levels, the counted reading.
    [pass_row] = db.query(SegmentPass, document_id=page1.id)
    segments = {s.kind: s for s in db.query(Segment, document_id=page1.id)}
    assert set(segments) == {"line", "word"}
    line, word = segments["line"], segments["word"]
    assert line.pass_id == word.pass_id == pass_row.id
    assert word.parent_segment_id == line.id
    assert line.anchor.document_id == page1.id
    readings = {r.level: r for r in db.query(ContentRepresentation, document_id=page1.id)}
    assert set(readings) == {"as_written", "expanded", "diplomatic"}
    assert readings["as_written"].segment_id == readings["expanded"].segment_id == line.id
    assert readings["diplomatic"].segment_id == word.id
    assert readings["diplomatic"].source_anchor.segment_id == word.id
    [choice] = db.query(ReadingChoice, document_id=page1.id)
    assert choice.representation_id == readings["as_written"].id and choice.segment_id == line.id

    # The artifact; the hand, matched by label and made in the target; the mark on the page.
    assert [a.content for a in db.query(Artifact, document_id=page1.id)] == ["Juan de la Cruz vende"]
    [attribution] = db.query(HandAttribution, segment_id=line.id)
    hand = db.get(Hand, attribution.hand_id)
    assert hand.label == "Hand A" and hand.scribe == "Escribano"
    assert hand.id != source.query(Hand, label="Hand A")[0].id
    assert [a.text for a in db.query(Annotation, document_id=page1.id)] == ["look"]

    # The canvas: the position and the link between the two pages travel, both ends mapped.
    [link_item] = db.query(CanvasItem, folder_id=folder_id)
    assert (link_item.source_item_id, link_item.target_item_id) == (page1.id, page2.id)
    [layout] = db.query(CanvasLayout, folder_id=folder_id)
    assert layout.id == f"{folder_id}::{page1.id}" and (layout.x, layout.y) == (10, 20)

    # Knowledge: the claim travels with its maker and state; the entity is written NEW and proposed.
    [claim] = [c for c in db.all(KnowledgeClaim) if c.text == "Juan de la Cruz sells a house"]
    assert claim.source_document_id == page1.id and claim.source_ids == [page1.id]
    assert claim.created_by == "maker" and claim.curation_state.value == "curated"
    carried = db.get(KnowledgeEntity, claim.subject_entity_id)
    assert carried.canonical_name == "Juan de la Cruz" and carried.id != box.target_entity.id
    assert carried.curation_state.value == "verified"  # a person's mark, kept
    assert db.get(KnowledgeEntity, box.target_entity.id).merged_into_id is None  # never merged by the transfer
    [proposal] = db.query(EntityMatchCandidate, candidate_entity_id=carried.id)
    assert proposal.survivor_entity_id == box.target_entity.id
    assert proposal.state == PendingMatchState.pending and proposal.method == PendingMatchMethod.transfer
    assert "wikidata" in proposal.reason.lower()
    [named] = [p for p in result["proposals"] if p["carried_entity"] == box.entity.id]
    assert named["proposal"] == proposal.id and named["target_entity"] == box.target_entity.id
    mention = [l for l in db.query(TypedLink, to_id=carried.id) if l.link_type == "names"]
    assert [m.from_id for m in mention] == [word.id]
    assert any(l.to_kind == "uri" for l in db.query(TypedLink, from_id=carried.id))  # its authority id travels

    # Cuts, listed by name: the claim's second source, the link to the page left behind, the canvas link to it.
    cuts = {(c["kind"], c["field"], c["points_to"], c["whole_row"]) for c in result["cuts"]}
    assert ("KnowledgeClaim", "source_ids", box.elsewhere.id, False) in cuts
    assert ("TypedLink", "to_id", box.elsewhere.id, True) in cuts
    assert ("CanvasItem", "target_item_id", box.elsewhere.id, True) in cuts
    assert not db.query(TypedLink, to_id=box.elsewhere.id)

    # Vocabulary: same key, different fields keeps the target's and names the difference.
    levels = {v["key"]: v for v in result["vocabulary"] if v["vocabulary"] == "reading_level"}
    assert levels["as_written"]["made"] is False and "Como se escribe" in levels["as_written"]["difference"]
    assert levels["diplomatic"]["made"] is True and levels["expanded"]["difference"] is None
    assert [v.label for v in db.query(LibraryReadingLevel, key="diplomatic")] == ["Diplomatic"]
    assert [v.label for v in db.query(LibraryReadingLevel, key="as_written")] == ["Como se escribe"]

    # Counts read back equal the plan, kind by kind.
    assert all(c["written"] == c["planned"] for c in result["counts"])
    # The record in both projects.
    assert db.get(TransferRecord, result["transfer_id"]).state.value == "done"
    assert source.get(TransferRecord, result["transfer_id"]).role.value == "source"
    # And the source is untouched.
    assert table_counts(source) == source_before


def test_no_carried_row_names_a_missing_row(client, db, tmp_path):
    """Scan every id field of every carried row: each names a row that is in the target."""
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    result = _copy(client, source_package, [box.folder.id]).json()
    record = db.get(TransferRecord, result["transfer_id"])
    carried = set(record.id_map.values())
    every_id = {row.id for model in db._all_schema_models() for row in db.all(model)}
    dangling = []
    for model in db._all_schema_models():
        for row in db.all(model):
            if row.id not in carried:
                continue
            for key, value in _mapped_values(row):
                if key != "PageLineMap.id" and value not in every_id:
                    dangling.append((key, value))
            assert not set(record.id_map) & {v for _k, v in _mapped_values(row)}, f"{row.id} keeps a source id"
    assert dangling == []


def test_a_dry_run_writes_nothing_and_says_what_a_copy_would(client, db, tmp_path):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    source_before, target_before = table_counts(source), table_counts(db)
    files_before = sorted((Path(db.path).parent / "files").rglob("*"))

    response = _copy(client, source_package, [box.folder.id], dry_run=True)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan["dry_run"] and plan["state"] == "planned" and plan["copies"] == [] and plan["audit"] is None
    assert table_counts(source) == source_before and table_counts(db) == target_before
    assert sorted((Path(db.path).parent / "files").rglob("*")) == files_before
    assert not db.all(TransferRecord) and not source.all(TransferRecord)

    counts = {c["kind"]: c["planned"] for c in plan["counts"]}
    assert counts["Document"] == 3 and counts["Segment"] == 2 and counts["KnowledgeEntity"] == 1
    assert plan["files"] == 1 and plan["bytes"] == Path(box.page1.path).stat().st_size
    assert [p["target_entity"] for p in plan["proposals"]] == [box.target_entity.id]
    assert any(v["vocabulary"] == "document_type" and v["key"] == "carta" and v["made"] for v in plan["vocabulary"])
    assert any(c["kind"] == "TypedLink" and c["whole_row"] for c in plan["cuts"])

    # And the copy then does what the plan said.
    done = _copy(client, source_package, [box.folder.id]).json()
    assert {c["kind"]: c["written"] for c in done["counts"]} == counts


def test_undo_of_a_copy_sends_it_to_the_targets_trash(client, db, tmp_path):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    result = _copy(client, source_package, [box.folder.id]).json()
    record = db.get(TransferRecord, result["transfer_id"])

    undone = client.post(f"/api/actions/audit/{result['audit']}/undo")
    assert undone.status_code == 200, undone.text
    copied_nodes = [db.get(Document, record.id_map[d]) for d in (box.folder.id, box.page1.id, box.page2.id)]
    assert all(node.deleted_at is not None for node in copied_nodes)  # in the target's Trash, not purged
    assert all(db.get(EntityMatchCandidate, p).state == PendingMatchState.withdrawn for p in record.proposals)
    assert db.get(TransferRecord, record.id).state.value == "undone"
    assert source.get(TransferRecord, record.id).state.value == "undone"
    assert source.get(Document, box.folder.id).deleted_at is None  # the source never changes on a copy's undo


def test_the_target_is_chosen_by_the_library_header(client, db, tmp_path):
    """The route's own library dependency picks the target, as the app sends it -- not a fixture."""
    from urllib.parse import quote

    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    header_decides(app)
    third = open_source(tmp_path, "Tercero.fichero")
    response = client.post("/api/documents/transfer", json={"items": [box.page1.id], "source": str(source_package)},
                           headers={"X-Fichero-Library-Path": quote(str(third), safe="/")})
    assert response.status_code == 200, response.text
    landed = db_manager.get_database(third).get(Document, response.json()["copies"][0])
    assert landed is not None and landed.name == "p1.png"
    assert db.get(Document, response.json()["copies"][0]) is None
