"""#6020: one JPG thumbnail alone and its hit-check, timed for information (printed with -s, no threshold)."""

import time
from pathlib import Path

from PIL import Image


def test_a_2000px_jpg_thumbnail_is_made_and_found_timed_for_information(db, test_package, tmp_path):
    from fichero_server.db.storage import ensure_thumbnail, get_thumbnail
    from fichero_server.importers.ingest import IngestMode, ingest_file

    source = tmp_path / "page.jpg"
    Image.effect_noise((2000, 1500), 80).convert("RGB").save(source, "JPEG", quality=90)
    package = Path(test_package)
    doc = ingest_file(source, mode=IngestMode.LINK, db=db, package_path=package,
                      extract_text=False, auto_embed=False)
    # a first call pays Pillow's import; the second is the steady state
    warm = tmp_path / "warm.jpg"
    Image.effect_noise((2000, 1500), 80).convert("RGB").save(warm, "JPEG", quality=90)
    warm_doc = ingest_file(warm, mode=IngestMode.LINK, db=db, package_path=package, extract_text=False, auto_embed=False)
    ensure_thumbnail(warm_doc, package_path=package, db=db)
    t0 = time.perf_counter()
    made = ensure_thumbnail(doc, package_path=package, db=db)
    make_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    hit = get_thumbnail(doc, package_path=package, db=db)
    hit_s = time.perf_counter() - t0
    print(f"\nthumbnail make {make_s * 1000:.1f} ms, hit-check {hit_s * 1000:.2f} ms")
    # the numbers are information (run with -s); a wall-clock threshold would flake on a loaded machine
    assert made is not None and hit == made


def test_the_hit_check_does_not_wait_for_a_writer_holding_the_gate(db, test_package, tmp_path):
    """An import's long transaction holds the DB's transaction gate; a thumbnail lookup must not queue behind it (#6020)."""
    import threading

    from fichero_server.db.storage import ensure_thumbnail, get_thumbnail
    from fichero_server.importers.ingest import IngestMode, ingest_file

    source = tmp_path / "page.jpg"
    Image.new("RGB", (800, 600), "white").save(source, "JPEG")
    package = Path(test_package)
    doc = ingest_file(source, mode=IngestMode.LINK, db=db, package_path=package, extract_text=False, auto_embed=False)
    made = ensure_thumbnail(doc, package_path=package, db=db)
    held, release = threading.Event(), threading.Event()

    def writer():
        with db._transaction_gate:
            held.set()
            release.wait(10)

    thread = threading.Thread(target=writer)
    thread.start()
    held.wait(5)
    try:
        result: list = []
        looker = threading.Thread(target=lambda: result.append(get_thumbnail(doc, package_path=package, db=db)))
        t0 = time.perf_counter()
        looker.start()
        looker.join(2)
        waited = time.perf_counter() - t0
        assert not looker.is_alive(), f"the hit-check is still waiting on the gate after {waited:.1f} s"
        assert result == [made]
    finally:
        release.set()
        thread.join()
