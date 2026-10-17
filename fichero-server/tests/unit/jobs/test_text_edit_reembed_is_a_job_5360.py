"""A direct edit of a page's text re-embeds it as a queued job, not inline on the request (#5360,
`activity.auto.reembed-on-change`): the request returns without paying the embed, and the job shows in Activity."""
from __future__ import annotations

from fichero_server.actions.page_text_cache import REEMBED_KIND
from fichero_server.execution import jobs
from fichero_server.models import DocType, Document


def test_a_direct_text_edit_queues_one_reembed_job_and_does_not_embed_inline(client, db, monkeypatch):
    doc = Document(name="Page", doc_type=DocType.file, page_content="before")
    db.save(doc)
    inline: list[str] = []
    monkeypatch.setattr(type(db), "embed", lambda self, d, *a, **k: inline.append(d.id))
    jobs.set_paused(True)  # nothing runs: what is queued is what is tested
    try:
        assert client.put(f"/api/documents/{doc.id}", json={"page_content": "after"}).status_code == 200
        assert client.put(f"/api/documents/{doc.id}", json={"page_content": "after again"}).status_code == 200
        waiting = db.execute_fetchall(
            "SELECT id FROM jobs WHERE kind = ? AND subject = ? AND state IN ('waiting', 'paused')",
            [REEMBED_KIND, doc.id],
        )
    finally:
        jobs.set_paused(False)

    assert inline == [], "the request does not embed"
    assert len(waiting) == 1, "two edits, one waiting job per page"
