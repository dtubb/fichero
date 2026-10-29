"""The import's names draft and a run's `read-names-again` for one page can run at the same moment, on two lanes: each
saw no `nlp_processed_at` and both drafted the same text (the names_once flake in
recipes/test_a_run_through_every_step.py). One page's draft runs one at a time; the second sees the first's mark."""

from __future__ import annotations

import threading

from fichero_server.importers import derivatives, nlp_draft
from fichero_server.models import DocType, Document, FileType, Status


def test_two_drafts_of_one_page_at_once_read_it_once(db, test_package, monkeypatch):
    doc = Document(name="p.md", doc_type=DocType.file, file_type=FileType.text,
                   status=Status.pending, page_content="Quito 1810.", language="es")
    db.save(doc)
    both_in = threading.Barrier(2, timeout=3)
    drafts = []

    def draft(db_, doc_):
        drafts.append(doc_.id)
        try:
            both_in.wait()  # the second draft gets here only if nothing keeps it out
        except threading.BrokenBarrierError:
            pass
        return nlp_draft.NlpDraftResult()

    monkeypatch.setattr(nlp_draft, "run_nlp_draft", draft)
    threads = [threading.Thread(target=derivatives._nlp_stage, args=(doc.id, test_package), kwargs=kw)
               for kw in ({}, {"after_correction": True})]
    for t in threads:
        t.start()
    for t in threads:
        t.join(15)
    assert drafts == [doc.id], f"one text drafted {len(drafts)} times"
