"""Regression test for #1554 — folder ingest must be thread-safe.

Root cause: ``ingest_folder`` fanned ``ingest_file(..., db=db, save=True)``
across a ``ThreadPoolExecutor`` that shared a single DuckDB ``Database``
connection. DuckDB connections are NOT thread-safe for concurrent
reads/writes. Under contention, ``Document`` read-backs returned ``None``
for required columns (``id``/``name``/``created_at``/``updated_at``),
tripping Pydantic validation. Those files were persisted as sourceless
``Status.failed`` stubs — no thumbnail, no preview, dropped forever.

Live log proof from the field::

    Failed to ingest …Preface-page9.jpeg: 4 validation errors for Document
    … id: Input should be a valid string [input_value=None]

for a *random subset* of pages each run.

Fix contract (asserted below):
  • Ingesting a folder of N files yields N successful Documents.
  • Zero ``Status.failed`` stubs are persisted (no race-induced failures).
  • Zero None-field validation failures.

The shared connection is now serialized behind a ``threading.Lock`` in
``ingest_folder``, eliminating the race deterministically while keeping
the existing executor structure and the failed-stub path for *genuine*
per-file errors (corrupt files etc.).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from fichero_server.db import Database
from fichero_server.importers.ingest import ingest_folder, IngestMode
from fichero_server.models import Document, Status

# A minimal-but-valid JPEG header so detect_file_type classifies these as
# images. Image files skip text extraction (_TEXT_EXTRACTABLE), so the
# ingest path is fast and deterministic — exactly the page-image scenario
# from the #1554 field report (Preface-pageN.jpeg).
_JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

# Enough files to push the executor to its max_workers and create real
# contention on the shared connection under the pre-fix code.
_NUM_FILES = 16


@pytest.fixture
def image_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "pages"
    folder.mkdir()
    for n in range(1, _NUM_FILES + 1):
        # Distinct bytes per file so checksums differ and none are
        # deduplicated away — every file must be ingested.
        (folder / f"Preface-page{n}.jpeg").write_bytes(
            _JPEG_BYTES + n.to_bytes(4, "big")
        )
    return folder


@patch("fichero_server.bookmarks.create_bookmark", return_value=None)
def test_folder_ingest_is_thread_safe_no_dropped_files(_mock_bookmark, image_folder, tmp_path):
    """Every file in the folder ingests successfully — zero failed stubs.

    Pre-fix (shared DuckDB connection across threads): a random subset of
    files come back as Status.failed stubs because the concurrent
    read-back returns None for required Document columns.

    Post-fix (db access serialized behind a lock): all files succeed.

    The race is probabilistic, so we run several full ingests to make the
    pre-fix failure overwhelmingly likely to surface at least once while
    keeping the post-fix run unconditionally green.
    """
    db = Database(tmp_path / "concurrency.duckdb")
    try:
        for _ in range(3):
            ingest_folder(
                image_folder,
                mode=IngestMode.LINK,
                db=db,
                # create_collection=True gives every file the SAME parent
                # folder, so each thread's ingest_file calls
                # _touch_ancestor_documents → concurrent db.get()+db.save()
                # on the *same* row. That is the highest-contention read-back
                # path and the one that nulled out Document columns in the
                # field (#1554).
                create_collection=True,
                # Match the field scenario: image pages, no text extraction.
                extract_text=False,
                auto_embed=False,
            )

            # Every input file that wasn't already ingested should come back.
            # After the first pass, hash-dedup means subsequent passes return
            # 0 new docs — but the invariant we care about (no failed stubs)
            # must hold on every pass.
            failed_stubs = [
                d for d in db.all(Document) if d.status == Status.failed
            ]
            assert not failed_stubs, (
                f"#1554 race regressed: {len(failed_stubs)} Status.failed stub(s) "
                f"persisted from a clean image folder — "
                f"{[d.name for d in failed_stubs]}"
            )

        # All distinct image files are present as successful, non-stub docs
        # with valid required fields (the columns the race nulled out).
        ingested = [
            d
            for d in db.all(Document)
            if d.name.startswith("Preface-page") and d.name.endswith(".jpeg")
        ]
        assert len(ingested) == _NUM_FILES, (
            f"expected {_NUM_FILES} image docs, got {len(ingested)}"
        )
        for d in ingested:
            assert d.status != Status.failed
            assert d.id and isinstance(d.id, str)
            assert d.name and isinstance(d.name, str)
            assert d.created_at is not None
            assert d.updated_at is not None
    finally:
        db.close()
