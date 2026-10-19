"""A sample try on pages whose originals are not on this Mac says so once, in words, and does not run (#5811).

Live 2026-10-19: every Find Lines sample try failed 28 times with `Kraken segmentation failed: [Errno 2] No such file
or directory: '/Users/.../1_Hoja_530_Recto.JPG'`. The pages were linked, not copied, and the originals were not here.
"""

from __future__ import annotations

from PIL import Image

from fichero_server.models import DocType, Document, FileType
from fichero_server.recipes import samples
from fichero_server.recipes.stages import get_stage


def _page(db, path) -> Document:
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
    db.save(doc)
    return doc


def test_a_try_on_a_missing_original_fails_once_with_the_fix_and_no_errno(db, tmp_path):
    gone = _page(db, tmp_path / "elsewhere" / "1_Hoja_530_Recto.JPG")
    out = samples._run_one(db, get_stage("find-lines"), {}, [gone.id], "job", "try-missing", name="Kraken")
    assert out["state"] == "failed"
    assert "Locate Originals" in out["error"]
    assert "original is not where this project says" in out["error"]
    assert "Errno" not in out["error"]
    assert out["ran"] == []


def test_a_try_on_present_originals_gets_past_the_check(db, tmp_path):
    here = tmp_path / "1_page.png"
    Image.new("RGB", (20, 20)).save(here)
    page = _page(db, here)
    from fichero_server.importers import relink

    assert relink.missing_originals(db, {page.id}) is None
