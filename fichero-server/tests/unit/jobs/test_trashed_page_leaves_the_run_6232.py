"""`activity.run.trashed-pages-leave-the-run` (#6232): a page whose document went to the Trash while it waited for the lane
is never read; its row ends "Skipped: the page was moved to the Trash" and the caller skips it as a stopped page (the run
goes on to its next page)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fichero_server.execution import jobs
from fichero_server.models import Document


def test_a_page_trashed_before_its_claim_is_skipped_and_the_next_is_read(db, monkeypatch):
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    jobs._ensure(db)
    for name in ("trashed", "kept"):
        db.save(Document(id=name, name=name))
    db.execute("UPDATE documents SET deleted_at = now() WHERE id = 'trashed'")
    library = str(db.path if Path(db.path).is_dir() else Path(db.path).parent)
    read: list[str] = []
    outcomes: dict[str, str] = {}

    async def page(doc_id):
        try:
            await jobs.run_on_lane(library, "read-a-page", doc_id, model="kraken:blla", fn=lambda: read.append(doc_id))
            outcomes[doc_id] = "done"
        except jobs.PageStopped:
            outcomes[doc_id] = "skipped"

    async def go():
        await page("trashed")
        await page("kept")

    asyncio.run(go())
    assert outcomes == {"trashed": "skipped", "kept": "done"}
    assert read == ["kept"]  # the trashed page's model pass never ran
    row = db.execute_fetchone("SELECT state, reason FROM jobs WHERE subject = 'trashed'")
    assert row == ("cancelled", jobs.TRASHED_PAGE)
