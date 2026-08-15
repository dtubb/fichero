"""get_committed: the gate-free read path for latency-critical GETs (#4523).

The live symptom: during a folder import, cached-thumbnail requests died with
deadlineExceeded because _document_or_404's db.get queued on the process-wide
transaction gate behind the ingest writer — off the event loop, but still
queued. get_committed reads last-committed state from a second connection
over the same DuckDB instance and must (a) answer while a writer holds the
gate, (b) NOT see uncommitted rows, and (c) survive read-cursor loss.
"""

import threading

from fichero_server.models import Document, DocType, SavedSearch


def _make_doc(name: str) -> Document:
    return Document(name=name, doc_type=DocType.folder)


class TestGetCommitted:
    def test_reads_committed_row(self, db):
        doc = _make_doc("committed-folder")
        db.save(doc)
        got = db.get_committed(Document, doc.id)
        assert got is not None
        assert got.name == "committed-folder"

    def test_missing_id_returns_none(self, db):
        assert db.get_committed(Document, "no-such-id") is None

    def test_answers_while_writer_holds_the_gate(self, db):
        """THE fire test: a reader must not queue behind an open transaction.

        A writer thread opens a transaction (taking the gate) and parks
        inside it. The main thread then calls get_committed — if it queues
        on the gate the way get() does, the 5s join expires and the test
        fails; the un-gated path answers immediately.
        """
        doc = _make_doc("visible-before-writer")
        db.save(doc)

        gate_held = threading.Event()
        release_writer = threading.Event()
        writer_error: list[Exception] = []

        def writer():
            try:
                with db.transaction():
                    inside = _make_doc("uncommitted-inside-open-tx")
                    inside.id = "uncommitted-doc-id"
                    db.save(inside)
                    gate_held.set()
                    # Hold the transaction open until the reader has proven
                    # both liveness and isolation.
                    release_writer.wait(timeout=10)
            except Exception as exc:  # pragma: no cover - surfaced below
                writer_error.append(exc)
                gate_held.set()

        result: dict[str, object] = {}

        def reader():
            result["visible"] = db.get_committed(Document, doc.id)
            result["uncommitted"] = db.get_committed(
                Document, "uncommitted-doc-id"
            )

        t_writer = threading.Thread(target=writer)
        t_writer.start()
        try:
            assert gate_held.wait(timeout=10), "writer never took the gate"
            assert not writer_error, f"writer failed: {writer_error}"

            t_reader = threading.Thread(target=reader)
            t_reader.start()
            t_reader.join(timeout=5)
            assert not t_reader.is_alive(), (
                "get_committed BLOCKED behind the open writer transaction — "
                "the gate-free read path is queueing on the gate"
            )

            visible = result["visible"]
            assert visible is not None and visible.name == "visible-before-writer"
            # Isolation: the writer's still-open row must be invisible.
            assert result["uncommitted"] is None
        finally:
            release_writer.set()
            t_writer.join(timeout=10)

    def test_recovers_after_read_cursor_loss(self, db):
        doc = _make_doc("survives-cursor-loss")
        db.save(doc)
        assert db.get_committed(Document, doc.id) is not None
        # Simulate invalidation: kill the dedicated read cursor outright.
        assert db._read_conn is not None
        db._read_conn.close()
        got = db.get_committed(Document, doc.id)
        assert got is not None and got.name == "survives-cursor-loss"

    def test_folded_models_route_to_gated_get(self, db):
        # SavedSearch is folded onto Document rows with special-case handling
        # in get(); get_committed must produce the same folded result (via
        # get), not misread the raw saved_searches/documents row shape.
        assert db.get_committed(SavedSearch, "no-such-search") is None
