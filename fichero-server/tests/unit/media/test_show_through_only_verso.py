"""A verso that is only the recto seen through the paper is marked, left out of reading by default through Leave Out's page-level
reason, included with one click, and the mark can be removed (`image.enhance.show-through-only-verso`, #6197). Fixtures are drawn."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from fichero_server.models import DocType, Document, FileType
from tests.unit.media.test_enhance_bleed_through import PAPER, _bars


def _grey_image(arr):
    return Image.fromarray(np.clip(np.stack([arr] * 3, axis=2), 0, 255).astype("uint8"))


def _recto_and_verso(own_writing=False, see=0.16):
    """A written recto and the page after it: the recto's ink mirrored and faint, or (own_writing) its own dark writing."""
    rng = np.random.default_rng(5)
    ink = _bars(1, 16)
    recto = PAPER + rng.normal(0, 2.0, ink.shape)
    recto[ink] = PAPER - 190.0
    verso = PAPER + rng.normal(0, 2.0, ink.shape)
    if own_writing:
        verso[_bars(9, 16)] = PAPER - 190.0
    else:
        verso[np.fliplr(ink)] = PAPER - see * 190.0
    return _grey_image(recto), _grey_image(verso)


def _docs(db, tmp_path, own_writing=False):
    recto, verso = _recto_and_verso(own_writing)
    out = []
    for name, image in (("recto.png", recto), ("verso.png", verso)):
        path = tmp_path / name
        image.save(path)
        doc = Document(name=name, doc_type=DocType.page, file_type=FileType.image, path=str(path), metadata={})
        db.save(doc)
        out.append(doc)
    return out


def test_a_faint_mirrored_verso_matches_and_a_verso_with_its_own_writing_does_not():
    from fichero_server.media import show_through_only as sto

    recto, verso = _recto_and_verso()
    got = sto.match(recto, verso)
    assert got["show_through_only"] is True and got["score"] >= sto.MATCH_MIN, got
    own_recto, own_verso = _recto_and_verso(own_writing=True)
    assert sto.match(own_recto, own_verso)["show_through_only"] is False
    blank = _grey_image(np.full(np.asarray(recto).shape[:2], PAPER))
    assert sto.match(blank, verso)["show_through_only"] is False, "a recto with no ink has nothing to show through"


def test_the_prepare_run_marks_the_verso_with_its_recto_and_leaves_the_recto_and_the_pixels_alone(db, tmp_path):
    import hashlib

    from fichero_server.recipes.runner import _run_prepare

    recto, verso = _docs(db, tmp_path)
    before = hashlib.sha256(open(verso.path, "rb").read()).hexdigest()
    step: dict = {}
    _run_prepare(db, [recto.id, verso.id], "run-1", step, paper=["show-through"], operations=[])
    marked = db.get(Document, verso.id).metadata
    assert marked["page_kind"] == "show-through-only" and marked["show_through_of"] == recto.id and marked["show_through_only"] is True
    assert "page_kind" not in (db.get(Document, recto.id).metadata or {})
    assert step["show_through_only"]["marked"] == 1
    assert hashlib.sha256(open(verso.path, "rb").read()).hexdigest() == before, "never rewritten, never deleted"


def test_without_the_show_through_answer_no_page_is_judged(db, tmp_path):
    from fichero_server.recipes.runner import _run_prepare

    recto, verso = _docs(db, tmp_path)
    step: dict = {}
    _run_prepare(db, [recto.id, verso.id], "run-1", step, paper=["faded"], operations=[])
    assert "show_through_only" not in step and "page_kind" not in (db.get(Document, verso.id).metadata or {})


def test_a_page_with_its_own_writing_is_not_marked(db, tmp_path):
    from fichero_server.recipes.runner import _run_prepare

    recto, verso = _docs(db, tmp_path, own_writing=True)
    _run_prepare(db, [recto.id, verso.id], "run-1", {}, paper=["show-through"], operations=[])
    assert "page_kind" not in (db.get(Document, verso.id).metadata or {})


def _invoke(db, tmp_path, name, **params):
    from fichero_server.actions.registry import ActionContext, registry

    return registry.invoke(db, name, params, ActionContext(actor="person", library_path=str(tmp_path), is_bootstrap=True))


def test_one_click_includes_the_verso_in_reading_and_back_and_clearing_the_mark_keeps_it_judged(db, tmp_path):
    from fichero_server.models import Segment
    from fichero_server.recipes import leave_out
    from fichero_server.recipes.runner import _run_prepare
    from tests.unit.recipes.test_leave_out_reads_page_box import _faint_line_page

    recto, verso = _docs(db, tmp_path)
    _run_prepare(db, [recto.id, verso.id], "run-1", {}, paper=["show-through"], operations=[])
    # a page of lines to read, carrying the verso's mark
    page, _ = _faint_line_page(db, tmp_path, enhanced_dark=True)
    page.metadata = {**db.get(Document, verso.id).metadata}
    db.save(page)
    leave_out.leave_out_pages(db, [page.id], "run-2")
    lines = [r for r in db.query(Segment, document_id=page.id) if r.kind == "line"]
    assert lines and all(r.is_furniture for r in lines), "left out by default"

    _invoke(db, tmp_path, "image.include_show_through_only", document_id=page.id, included=True)
    assert db.get(Document, page.id).metadata["show_through_included"] is True
    _invoke(db, tmp_path, "image.include_show_through_only", document_id=page.id, included=False)
    assert db.get(Document, page.id).metadata["show_through_included"] is False

    _invoke(db, tmp_path, "image.clear_show_through_only", document_id=verso.id)
    meta = db.get(Document, verso.id).metadata
    assert "page_kind" not in meta and "show_through_only" not in meta and meta["show_through_checked"] is True
    with pytest.raises(Exception):
        _invoke(db, tmp_path, "image.include_show_through_only", document_id=verso.id)
