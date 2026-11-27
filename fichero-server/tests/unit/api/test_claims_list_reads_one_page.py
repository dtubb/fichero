"""An unfiltered claims list reads one page of rows, not the whole table (perf-optimize, 2026-11-27).

Measured at origin/integration with 6,000 statements: `GET /api/claims?limit=500` hydrated all 6,000 (`db.all`) to answer 500,
641 ms, almost all of it parsing JSON columns of rows the page never showed. A project-size library has 50,000. With no filter
and nothing in the Trash the page is a bounded read in table order; a filter or a trashed page keeps the full read, whose
rule stays in Python (`visible_claims`).
"""
from __future__ import annotations

from datetime import datetime

from fichero_server.models.knowledge import ClaimCurationState, KnowledgeClaim

N_CLAIMS = 600


def _seed(db) -> list[KnowledgeClaim]:
    now = datetime.now()
    claims = [
        KnowledgeClaim(text=f"Statement {i}.", source_document_id=None, entity_ids=[], curation_state=ClaimCurationState.unreviewed,
                       created_at=now, updated_at=now)
        for i in range(N_CLAIMS)
    ]
    assert db.save_many(claims) == N_CLAIMS
    return claims


def test_an_unfiltered_page_never_reads_the_whole_table(db, client, monkeypatch):
    _seed(db)
    whole = [c.id for c in db.all(KnowledgeClaim)]

    def refuse(*a, **k):
        raise AssertionError("the whole statements table was read for one page")

    monkeypatch.setattr(db, "all", refuse)
    for offset in (0, 50, 550):
        r = client.get("/api/claims", params={"limit": 50, "offset": offset})
        assert r.status_code == 200, r.text
        assert [c["id"] for c in r.json()["items"]] == whole[offset:offset + 50], "the page is the same slice, in table order"


def test_a_filtered_page_still_reads_through_the_filter(db, client):
    _seed(db)
    r = client.get("/api/claims", params={"limit": 50, "q": "Statement 59"})
    assert r.status_code == 200, r.text
    texts = [c["text"] for c in r.json()["items"]]
    assert len(texts) == 11 and all("Statement 59" in t for t in texts), texts  # 59 and 590 to 599
