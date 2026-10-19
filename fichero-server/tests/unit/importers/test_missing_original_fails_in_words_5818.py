"""A page whose original is missing fails its thumbnail job in words and the job ends (#5818).

WHY: the owner's 'Demo Test Small' left its pages in place; four originals were gone. Their thumbnail jobs ended
'done' with nothing said, so the run behind them never learned a page had failed. The job must fail with the
sentence #5811 gives a try, naming the file.
"""

from __future__ import annotations

import pytest

from fichero_server.importers import derivatives
from fichero_server.models import DocType, Document, FileType


def _gone(db, tmp_path) -> Document:
    path = tmp_path / "away" / "LFH_IMG_001.jpg"
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path),
                   metadata={"ingest_mode": "link", "source_path": str(path)})
    db.save(doc)
    return doc


def test_a_missing_original_says_where_to_look(db, tmp_path):
    doc = _gone(db, tmp_path)
    said = derivatives._source_error(doc, db, str(db.path.parent))
    assert said == "LFH_IMG_001.jpg isn't where it was imported from: Locate Originals…"


def test_the_thumbnail_job_fails_with_that_sentence(db, tmp_path):
    doc = _gone(db, tmp_path)
    with pytest.raises(derivatives.SourceMissing, match="LFH_IMG_001.jpg isn't where it was imported from"):
        derivatives._thumbnail_job(db, doc.id)
    assert "isn't where" in db.get(Document, doc.id).metadata["derivative_error"]


def test_a_direct_stage_call_still_just_returns_none(db, tmp_path):
    doc = _gone(db, tmp_path)
    assert derivatives._thumbnail_stage(doc.id, str(db.path.parent)) is None
