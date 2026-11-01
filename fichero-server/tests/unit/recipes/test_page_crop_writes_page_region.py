"""Finding the page writes the `page_region` attribute beside `page_box` (`prep.page.region-attribute-and-page-box`, #6187, #6198).

WHY: Preview draws the corners and Squaring warps from them; Leave Out and Find Regions read the box. One finding, both.
"""
from __future__ import annotations

from pathlib import Path

from fichero_server.models import DocType, Document, FileType
from tests.unit.media.test_find_page import PAGE, H, W, scan


def test_page_crop_writes_page_region_and_the_same_page_box(db, tmp_path, monkeypatch):
    from fichero_server.media import find_page as module
    from fichero_server.recipes.page_crop import crop_pages

    monkeypatch.setattr(module, "find_page_vision", lambda image: None)
    path = tmp_path / "scan.png"
    scan().save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)

    account = crop_pages(db, [doc.id], "run-1")

    meta = db.get(Document, doc.id).metadata
    region = meta["page_region"]
    assert account["cropped"] == 1
    assert region["box"] == meta["page_box"] and region["method"] == "contour" and region["frame"] == "upright"
    assert len(region["quad"]) == 4 and 0.8 <= region["confidence"] <= 1.0
    assert abs(region["box"][0] - PAGE[0] / W) < 0.02 and abs(region["box"][1] - PAGE[1] / H) < 0.02


def test_page_crop_keeps_the_pages_other_metadata_over_two_runs(db, tmp_path, monkeypatch):
    """Review HIGH 1: `document.update` replaces the whole metadata object. A cut page (`split_source_id`), a person's
    Unhide (`blank`) and an answered proposal (`prep_answered`) must survive a page-box write on every run."""
    from fichero_server.media import find_page as module
    from fichero_server.recipes.done import _is_split_page, pages_for
    from fichero_server.recipes.page_crop import crop_pages

    monkeypatch.setattr(module, "find_page_vision", lambda image: None)
    path = tmp_path / "scan.png"
    scan().save(path)
    source = Document(name="photo.png", doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(source)
    person_blank = {"blank": False, "by": "person", "reason": "unhidden by a person"}
    kept = {"split_source_id": source.id, "blank": person_blank, "prep_answered": {"turn": True}}
    cut = Document(name="cut.png", doc_type=DocType.chunk, file_type=FileType.image, path=str(path), metadata=dict(kept))
    db.save(cut)

    for run in ("run-1", "run-2"):
        assert crop_pages(db, [cut.id], run, prepare=True)["cropped"] == 1
        meta = db.get(Document, cut.id).metadata
        assert {k: meta[k] for k in kept} == kept, run
        assert "page_box" in meta and "page_region" in meta

    assert _is_split_page(db.get(Document, cut.id))
    assert cut.id in pages_for(db, {}, None)
    assert not db.get(Document, cut.id).exclude_from_processing


def test_a_page_prepared_from_the_same_file_is_not_found_again_on_the_next_run(db, tmp_path, monkeypatch):
    """Review MED 4 (Stage 2): a fresh `crop_pages` recomputed every page. With `reuse`, a stamped page (same file, same
    rules) is `unchanged` and no finder runs; a changed file is prepared again."""
    from fichero_server.media import find_page as module
    from fichero_server.recipes import page_crop

    calls = []
    real = module.find_page_contour
    monkeypatch.setattr(module, "find_page_vision", lambda image: None)
    monkeypatch.setattr(module, "find_page_contour", lambda image: calls.append(1) or real(image))
    path = tmp_path / "scan.png"
    scan().save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)

    assert page_crop.crop_pages(db, [doc.id], "run-1", prepare=True, reuse=True)["cropped"] == 1
    again = page_crop.crop_pages(db, [doc.id], "run-2", prepare=True, reuse=True)
    assert again["unchanged"] == 1 and again["pages"] == 0 and len(calls) == 1

    assert page_crop.crop_pages(db, [doc.id], "run-3", prepare=True)["cropped"] == 1  # no reuse asked: recomputed
    assert len(calls) == 2

    scan(ruler=False).save(path)  # the file changed
    assert page_crop.crop_pages(db, [doc.id], "run-4", prepare=True, reuse=True)["unchanged"] == 0
    assert len(calls) == 3


def test_curated_exclusion_and_a_cut_page_survive_crop_pages_not_only_mark_blank(db, tmp_path, monkeypatch):
    """Review MED 7: `done._is_split_page` and the unit-of-work query read `metadata.blank`. Through `crop_pages` (which writes
    the page box), a page a person curated out and a chunk cut from a photograph keep their state, so a run counts both."""
    from fichero_server.media import find_page as module
    from fichero_server.recipes.done import pages_for
    from fichero_server.recipes.page_crop import crop_pages

    monkeypatch.setattr(module, "find_page_vision", lambda image: None)
    path = tmp_path / "scan.png"
    scan().save(path)
    source = Document(name="photo.png", doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    curated = Document(name="curated.png", doc_type=DocType.page, file_type=FileType.image, path=str(path), metadata={},
                       exclude_from_processing=True)
    db.save(source)
    db.save(curated)
    cut = Document(name="cut.png", doc_type=DocType.chunk, file_type=FileType.image, path=str(path),
                   metadata={"split_source_id": source.id})
    db.save(cut)
    before = set(pages_for(db, {}, None))

    crop_pages(db, [curated.id, cut.id], "run-1", prepare=True)
    crop_pages(db, [curated.id, cut.id], "run-2", prepare=True)

    assert curated.id in set(pages_for(db, {}, None)) and cut.id in set(pages_for(db, {}, None))
    assert set(pages_for(db, {}, None)) == before
    assert db.get(Document, curated.id).exclude_from_processing is True
    assert db.get(Document, cut.id).metadata["split_source_id"] == source.id




def test_a_page_prepared_again_keeps_its_image_signature_so_read_does_not_read_it_again(db, tmp_path, monkeypatch):
    """Trace of PREP_VERSION 3: a stamp that no longer holds prepares the page again. The renditions it writes were named by a
    fresh uuid, so the image signature (the file name) changed and `unread_by` counted every reading as made from another
    image. Named by its bytes, the same pixels give the same name (same input + same model: reuse, never rerun)."""
    from fichero_server.media import find_page as module
    from fichero_server.models import Rendition
    from fichero_server.recipes import page_crop

    monkeypatch.setattr(module, "find_page_vision", lambda image: None)
    path = tmp_path / "scan.png"
    scan().save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)

    def names():
        return sorted(Path(r.path).name for r in db.query(Rendition, document_id=doc.id))

    assert page_crop.crop_pages(db, [doc.id], "run-1", prepare=True)["cropped"] == 1
    first = names()
    assert first
    assert page_crop.crop_pages(db, [doc.id], "run-2", prepare=True)["cropped"] == 1
    assert names() == first


def _skewed_whole_page(path):
    """A ruled scan whose paper fills the frame (no page to cut), its lines turned 4 degrees: Prepare would straighten it."""
    from PIL import Image, ImageDraw

    page = Image.new("RGB", (900, 700), (235, 230, 215))
    draw = ImageDraw.Draw(page)
    for y in range(80, 640, 40):
        draw.line([(40, y), (860, y)], fill=(40, 40, 70), width=3)
    page.rotate(4, resample=Image.Resampling.BICUBIC, fillcolor=(235, 230, 215)).save(path)


def _prepared_roles(db, tmp_path, monkeypatch, read):
    from fichero_server.media import find_page as module
    from fichero_server.models import Rendition
    from fichero_server.recipes import page_crop

    monkeypatch.setattr(module, "find_page_vision", lambda image: None)
    path = tmp_path / "skewed.png"
    _skewed_whole_page(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)
    read(doc)
    page_crop.crop_pages(db, [doc.id], "run-1", prepare=True)
    return sorted(r.role for r in db.query(Rendition, document_id=doc.id))


def _whole_page_reading(db):
    from fichero_server.models import Artifact

    return lambda doc: db.save(Artifact(document_id=doc.id, artifact_type="transcription", model="m", provider="p", content="texto"))


def _line_reading(db):
    from fichero_server.models import Artifact, ContentRepresentation
    from fichero_server.models.anchors import SourceAnchor

    def read(doc):
        art = Artifact(document_id=doc.id, artifact_type="kraken-lines", model="m", provider="kraken")
        db.save(art)
        db.save(ContentRepresentation(document_id=doc.id, kind="transcription", segment_id="line-1", derived_from_artifact_id=art.id,
                                     content="texto", source_anchor=SourceAnchor(document_id=doc.id)))

    return read


def test_an_unread_skewed_whole_page_is_straightened(db, tmp_path, monkeypatch):
    """The control: with no reading the operations still run on a page left whole."""
    assert _prepared_roles(db, tmp_path, monkeypatch, lambda doc: None)


def test_a_skewed_whole_page_read_by_a_direct_run_keeps_the_image_it_was_read_from(db, tmp_path, monkeypatch):
    """Review 8 M1: turning a page already read changed the image its reading came from, so the skip-if-done lookup sent it again."""
    assert _prepared_roles(db, tmp_path, monkeypatch, _whole_page_reading(db)) == []


def test_a_skewed_whole_page_half_read_keeps_the_image_it_was_read_from(db, tmp_path, monkeypatch):
    """Review 8 M1: a page stopped half-read asked for every line again once Prepare had turned it (`unread_by`)."""
    assert _prepared_roles(db, tmp_path, monkeypatch, _line_reading(db)) == []


def test_a_rendition_write_cut_short_is_written_again(db, tmp_path, monkeypatch):
    """Review 8 M2: a half PNG under the hash name was kept for good; written to `.part` and replaced, and a short file is redone."""
    from fichero_server.media import find_page as module
    from fichero_server.models import Rendition
    from fichero_server.recipes import page_crop

    monkeypatch.setattr(module, "find_page_vision", lambda image: None)
    path = tmp_path / "scan.png"
    scan().save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)
    page_crop.crop_pages(db, [doc.id], "run-1", prepare=True)
    stored = Path(db.query(Rendition, document_id=doc.id)[0].path)
    whole = stored.read_bytes()
    stored.write_bytes(whole[: len(whole) // 2])  # a crash mid-write
    page_crop._write(db, doc, stored.name.split("_")[1], __import__("PIL.Image").Image.open(__import__("io").BytesIO(whole)),
                     "run-2", Path(db.path).parent, "again", [0, 0, 1, 1], None)
    assert stored.read_bytes() == whole and not list(stored.parent.glob("*.part"))
