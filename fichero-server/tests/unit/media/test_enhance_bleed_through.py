"""Bleed-through suppression as an enhancement step (`image.enhance.bleed-through-suppression`, #6196). The pair is drawn: a
recto with strong ink and the verso's writing showing through it faintly and mirrored, and the verso scan itself."""
from __future__ import annotations

import asyncio
import io

import numpy as np
import pytest
from PIL import Image

from fichero_server.models import Document, FileType, Rendition

H, W = 400, 600
PAPER = 235.0


def _bars(seed, n):
    """Short thick bars standing in for lines of writing; a boolean H x W mask."""
    rng = np.random.default_rng(seed)
    mask = np.zeros((H, W), bool)
    for _ in range(n):
        y, x = int(rng.integers(30, H - 30)), int(rng.integers(30, W - 140))
        mask[y:y + 4, x:x + int(rng.integers(40, 120))] = True
    return mask


def _pair(shift=(0, 0), see=0.16, ink_darkness=190.0):
    """(recto, verso, masks): the recto's ink, the show-through placed where the verso's writing lies seen from the recto; `shift` is how far the verso scan sits from that."""
    rng = np.random.default_rng(11)
    recto_ink, verso_in_recto_frame = _bars(1, 14), _bars(2, 14)
    dx, dy = shift
    through = verso_in_recto_frame & ~recto_ink
    recto = PAPER + rng.normal(0, 2.0, (H, W))
    recto[verso_in_recto_frame] -= see * ink_darkness
    recto[recto_ink] = PAPER - ink_darkness
    verso = PAPER + rng.normal(0, 2.0, (H, W))
    # the verso scan: its own writing, mirrored, and sitting (dx, dy) pixels off where it shows through the recto
    verso[np.fliplr(np.roll(np.roll(verso_in_recto_frame, dy, axis=0), dx, axis=1))] = PAPER - ink_darkness
    to_image = lambda g: Image.fromarray(np.clip(np.stack([g] * 3, axis=2), 0, 255).astype("uint8"))  # noqa: E731
    return to_image(recto), to_image(verso), recto_ink, through


def _grey(image):
    return np.asarray(image.convert("L"), "float32")


def test_method_a_pushes_the_show_through_to_the_paper_and_does_not_thin_the_ink():
    from fichero_server.media.enhance import bleed_through

    recto, _, ink, through = _pair()
    before = _grey(recto)
    assert PAPER - before[through].mean() > 25, "the fixture's show-through is visible"
    out, account = bleed_through.run(recto, bleed_through.Params())
    after = _grey(out)
    assert account["step"] == "bleed-through" and account["method"] == "a" and account["applied"] is True
    assert abs(after[through].mean() - np.median(before[~through & ~ink])) < 6, after[through].mean()
    assert np.array_equal(after[ink], before[ink]), "the ink's pixels are unchanged"
    assert (after < 120).sum() == (before < 120).sum(), "the ink is not thinned"


def test_method_a_on_a_page_with_no_ink_returns_it_unchanged():
    from fichero_server.media.enhance import bleed_through

    blank = Image.new("RGB", (200, 120), (235, 235, 235))
    out, account = bleed_through.run(blank, bleed_through.Params())
    assert out.tobytes() == blank.tobytes() and account["applied"] is False


@pytest.mark.parametrize("shift", [(6, 4), (-8, 3)])
def test_method_b_registers_the_mirrored_verso_and_subtracts_its_share_leaving_the_ink_alone(shift):
    from fichero_server.media.enhance import bleed_through

    recto, verso, ink, through = _pair(shift=shift)
    before = _grey(recto)
    out, account = bleed_through.run(recto, bleed_through.Params(method="b"), verso=verso)
    after = _grey(out)
    assert account["applied"] is True, account
    assert 0.08 < account["gain"] < 0.3, account  # the fixture's share is 0.16
    assert abs(after[through].mean() - np.median(before[~through & ~ink])) < 6, after[through].mean()
    assert np.array_equal(after[ink], before[ink])


def test_without_the_registration_the_same_pair_is_not_cleaned(monkeypatch):
    """The shift is real: with the verso laid on the recto as it is, the share fitted is near zero and the show-through stays."""
    import cv2

    from fichero_server.media.enhance import bleed_through

    recto, verso, ink, through = _pair(shift=(6, 4))
    monkeypatch.setattr(bleed_through, "register_verso", lambda r, v: (np.eye(2, 3, dtype=np.float32), cv2.flip(cv2.resize(v, (r.shape[1], r.shape[0])), 1)))
    out, account = bleed_through.run(recto, bleed_through.Params(method="b"), verso=verso)
    assert account["gain"] < 0.05 and PAPER - _grey(out)[through].mean() > 25


def test_method_b_without_a_verso_says_so_and_returns_the_page():
    from fichero_server.media.enhance import bleed_through

    recto, *_ = _pair()
    out, account = bleed_through.run(recto, bleed_through.Params(method="b"))
    assert out.tobytes() == recto.tobytes() and account["applied"] is False and account["reason"] == "no verso"


def _document(db, image, name):
    path = db.path.parent / "files" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    doc = Document(name=name, path=str(path), file_type=FileType.image)
    db.save(doc)
    return doc


def test_three_sample_pages_preview_through_the_routes_and_the_original_is_untouched(client, db):
    seen = []
    for index, seed_shift in enumerate([(0, 0), (3, 2), (-4, 1)]):
        recto, *_ = _pair(shift=seed_shift)
        doc = _document(db, recto, f"p{index}.png")
        before = open(doc.path, "rb").read()
        refused = client.put(f"/api/images/{doc.id}/edits", json={"operations": [{"op": "bleed_through", "params": {"k": 0.9}}]})
        assert refused.status_code == 422, refused.text
        put = client.put(f"/api/images/{doc.id}/edits", json={"operations": [{"op": "bleed_through", "params": {"method": "a"}}]})
        assert put.status_code == 200, put.text
        got = client.get(f"/api/images/{doc.id}/preview")
        assert got.status_code == 200, got.text[:200]
        shown = _grey(Image.open(io.BytesIO(got.content)))
        seen.append(float(np.abs(shown - _grey(recto)).mean()))
        assert open(doc.path, "rb").read() == before
    assert all(change > 0.3 for change in seen), seen


def test_the_node_with_method_b_takes_the_verso_from_versos_and_records_the_step(db):
    from fichero_server.workflows.tools import enhance_step_nodes

    recto, verso, _, _ = _pair(shift=(5, 3))
    doc = _document(db, recto, "recto.png")
    verso_path = db.path.parent / "files" / "verso.png"
    verso.save(verso_path)
    state = {"library_path": str(db.path.parent), "run_id": "run-2", "batch_id": "batch-2"}
    out = asyncio.run(enhance_step_nodes.bleed_through_images(
        {"files": [doc.path], "versos": [str(verso_path)], "documents": [{"id": doc.id}], "method": "b", "output_format": "png"},
        state, None))
    assert out["error"] is None and out["count"] == 1, out
    (row,) = db.query(Rendition, document_id=doc.id)
    assert row.role == "enhanced" and row.steps[0]["step"] == "bleed-through"
    assert row.steps[0]["params"] == {"method": "b"} and row.steps[0]["card"]["method"] == "b"
    missing = asyncio.run(enhance_step_nodes.bleed_through_images(
        {"files": [doc.path], "documents": [{"id": doc.id}], "method": "b", "output_format": "png"}, state, None))
    assert missing["error"] and "verso" in missing["error"]
