"""#5690: a recipe's Names step is not starved by the import's NLP drafts at the one spaCy lock.

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md (`activity.waiting-says-why`). WHY (2026-10-11,
the MCP onboarding walk): Names sat at 0 of 92 for 15+ minutes with no waiting reason while "Processing imported
pages" ran. Both read names with spaCy under one process-wide lock (a spaCy pipeline is not thread-safe), and the
drafts' loop took it again page after page: a plain lock is not fair, so the step a person started never got a
turn, and it had no row to say so. Work a person started goes first; the drafts wait while it waits. The pipeline
is a stub; the lock and the order are the real ones.
"""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from fichero_server.knowledge import spacy_ner


def test_a_step_a_person_started_goes_before_the_import_drafts(monkeypatch):
    def nlp(text):
        until = time.perf_counter() + 0.01  # a page's inference, holding the lock and the GIL, as spaCy's does
        while time.perf_counter() < until:
            pass
        return SimpleNamespace(ents=[])

    monkeypatch.setattr(spacy_ner, "_load_pipeline", lambda lang: nlp)
    drafts_done = 0
    stop = threading.Event()

    def drafts():
        nonlocal drafts_done
        while not stop.is_set():
            spacy_ner.extract_entities("vendió Juan una casa", language="es", background=True)
            drafts_done += 1

    worker = threading.Thread(target=drafts, daemon=True)
    worker.start()
    time.sleep(0.05)  # the drafts hold the lock, page after page
    before = drafts_done
    assert before > 0 and worker.is_alive(), "the drafts are reading names"
    spacy_ner.extract_entities("Don Juan de Mosquera", language="es")
    waited_for = drafts_done - before
    stop.set()
    worker.join(timeout=5)
    assert waited_for <= 2, f"the step waited behind {waited_for} drafts"
