"""Health answers while a writer holds the library's transaction gate (`engine.health-answers-under-load`, #6178).

WHY: the app's heartbeat carries the library header, and health counted the open library's documents through the gated
connection, so a long write (a Kraken save, an import's embeds) held the answer, the app counted missed pings and
restarted a working engine.
"""
from __future__ import annotations

import threading

from fichero_server.db import db_manager
from fichero_server.models import DocType, Document, Status


def test_health_with_a_library_answers_while_a_writer_holds_the_gate(client, test_package):
    db = db_manager.get_database(test_package)
    db.save(Document(name="letter.jpg", doc_type=DocType.file, status=Status.pending))
    held, release = threading.Event(), threading.Event()

    def writer():
        with db._transaction_gate:
            held.set()
            release.wait(60)  # released below; the ceiling only frees a broken run

    holder = threading.Thread(target=writer, name="test-gate-holder", daemon=True)
    holder.start()
    assert held.wait(5)
    answers: list = []
    asker = threading.Thread(target=lambda: answers.append(client.get("/api/health")), daemon=True)
    try:
        asker.start()
        asker.join(5)
        assert answers, "health waited on the writer's transaction gate"
    finally:
        release.set()
        holder.join(10)
        asker.join(10)
    body = answers[0].json()
    assert answers[0].status_code == 200 and body["status"] == "healthy"
    assert body["document_count"] == 1, "the count is the committed one, read beside the writer"
