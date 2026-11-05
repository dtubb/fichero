"""`safety.trash.every-read-leaves-it-out` (#5406): the guard refuses a GET handler that reads a Trash-hidden kind without the seam."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_trash_seam_reads as guard  # noqa: E402


def _routes(tmp_path, body: str) -> Path:
    (tmp_path / "area").mkdir()
    (tmp_path / "area" / "reads.py").write_text(body)
    return tmp_path


def test_a_get_handler_reading_claims_without_the_seam_is_found(tmp_path):
    routes = _routes(tmp_path, '''
@router.get("/claims")
def leaky(db):
    return db.query(KnowledgeClaim)
''')
    examined, found = guard.scan(routes)
    assert examined == 1
    assert found == {"area/reads.py::leaky": ["KnowledgeClaim"]}


def test_a_handler_through_the_seam_or_a_write_or_another_kind_is_clean(tmp_path):
    routes = _routes(tmp_path, '''
@router.get("/claims")
def seamed(db):
    return visible_claims(db, db.query(KnowledgeClaim))

@router.get("/trash-aware")
def asks_for_the_trash(db):
    gone = trashed_document_ids(db)
    return [c for c in db.query(KnowledgeClaim) if c.source_document_id not in gone]

@router.post("/claims")
def writes(db):
    return db.query(KnowledgeClaim)

@router.get("/segments")
def other_kind(db):
    return db.query(Segment)
''')
    _examined, found = guard.scan(routes)
    assert found == {}


def test_the_repo_has_no_unlisted_leak():
    _examined, found = guard.scan()
    assert set(found) <= set(guard.load_known_gaps()), "a new read without the Trash seam"
