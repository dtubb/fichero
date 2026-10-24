"""#6019: a thumbnail that was made is found by the next ask (get_thumbnail), and ensure_thumbnail takes the hit path."""

from pathlib import Path

from PIL import Image


def _jpg_doc(db, test_package, tmp_path):
    from fichero_server.importers.ingest import IngestMode, ingest_file

    source = tmp_path / "page.jpg"
    Image.new("RGB", (1600, 1200), "white").save(source, "JPEG")
    return ingest_file(source, mode=IngestMode.LINK, db=db, package_path=Path(test_package),
                       extract_text=False, auto_embed=False)


def test_a_made_thumbnail_is_found_next_time(db, test_package, tmp_path):
    from fichero_server.db.storage import ensure_thumbnail, get_thumbnail

    doc = _jpg_doc(db, test_package, tmp_path)
    package = Path(test_package)
    made = ensure_thumbnail(doc, package_path=package, db=db)
    assert made is not None
    assert get_thumbnail(doc, package_path=package, db=db) == made, "the hit-check does not find what was just made"
    mtime = made.stat().st_mtime_ns
    assert ensure_thumbnail(doc, package_path=package, db=db) == made
    assert made.stat().st_mtime_ns == mtime, "the second ask rewrote the thumbnail"
