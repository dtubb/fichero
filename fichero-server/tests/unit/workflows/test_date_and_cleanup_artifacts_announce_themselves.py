"""#4890's last two tools: `date_extract` and `cleanup` announce their artifacts.

Both wrote an artifact and told nobody. Neither could be fixed with the key
`collect_created_artifact_ids` reads, because neither captured an id at all —
each artifact was constructed inside its own `db.save(...)` call, so there was
nothing to report even if the return had had somewhere to put it.

`date_extract` is the sharper of the two: it ALREADY emitted a document event for
the pages whose date columns moved, and said nothing about the `dates` artifacts.
A page whose columns did not move still gets a new artifact recording which kind
of nothing was found — so tying the artifact event to the document event would
have reproduced #4890's cause exactly, an artifact event riding on a change to
something else.
"""

from __future__ import annotations

import inspect

from unittest.mock import MagicMock, patch

from fichero_server.workflows.tools import cleanup as cleanup_tool


class TestCleanupsReplacementSaysSo:
    def _replace(self, *, save_raises: bool = False) -> list[dict]:
        emitted: list[dict] = []
        db = MagicMock()
        db.query.return_value = []
        if save_raises:
            db.save.side_effect = RuntimeError("disk full")

        with (
            patch.object(cleanup_tool, "sweep_replaceable", create=True, return_value=([], [])),
            patch(
                "fichero_server.workflows.curation_guard.sweep_replaceable",
                return_value=([], []),
            ),
            patch(
                "fichero_server.workflows.tools._workflow_change_emit"
                ".emit_workflow_artifact_changes_for_db",
                lambda db, **kwargs: emitted.append(kwargs),
            ),
        ):
            cleanup_tool._replace_artifact(
                db, "folder-1", "people_clean",
                [{"canonical": "Ana"}, {"canonical": "Beatriz"}],
                "mock", "mock-1",
            )
        return emitted

    def test_the_fresh_artifact_and_its_container_are_named(self):
        emitted = self._replace()

        assert len(emitted) == 1
        assert emitted[0]["document_ids"] == ["folder-1"]
        assert len(emitted[0]["artifact_ids"]) == 1

    def test_a_save_that_failed_announces_nothing(self):
        """The save is already wrapped in a try/except that warns. An event after a
        failed write would send a subscriber to refetch an artifact that is not
        there — worse than the silence this fix removes, because it looks like
        success."""
        assert self._replace(save_raises=True) == []

    def test_the_emit_lives_in_the_helper_both_call_sites_use(self):
        """Why it is not at the call sites: there are two, and a rule applied in one
        place cannot be applied in one place only."""
        source = inspect.getsource(cleanup_tool)
        assert source.count("_replace_artifact(") >= 3  # the def plus both callers
        assert source.count("emit_workflow_artifact_changes_for_db(") == 1


class TestDateExtractSeparatesTheTwoEvents:
    def test_the_artifact_emit_is_not_folded_into_the_document_emit(self):
        """Pins the shape, which is the thing that would silently regress: a later
        edit folding the two emits together would restore #4890's cause — an
        artifact event that only fires when a document changed."""
        from fichero_server.workflows.tools import date_extract

        source = inspect.getsource(date_extract)
        assert "emit_workflow_document_changes(" in source
        assert "emit_workflow_artifact_changes(" in source
        # Two separate guards, on two separate lists.
        assert "if changed_ids:" in source
        assert "if dated_artifact_ids:" in source

    async def test_running_the_tool_announces_the_artifact_it_wrote(self):
        """The behavioural half: run the real tool over one document and read what
        went onto the change stream. The source checks above pin the shape; this
        proves the event happens at all.
        """
        from fichero_server.models import Document, DocType, FileType, Status
        from fichero_server.workflows.tools import date_extract

        doc = Document(
            name="1817 padron.jpg", doc_type=DocType.file, file_type=FileType.image,
            status=Status.completed, page_content="Hecho en el año de 1817",
        )
        saved: list = []
        emitted: list[dict] = []
        db = MagicMock()
        db.get.return_value = doc
        db.save.side_effect = lambda row: saved.append(row)

        with (
            patch("fichero_server.db.db_manager.get_database", return_value=db),
            patch.object(
                date_extract, "emit_workflow_artifact_changes",
                lambda library_path, **kwargs: emitted.append(kwargs),
            ),
            patch.object(date_extract, "emit_workflow_document_changes", lambda *a, **k: None),
        ):
            await date_extract.date_extract_tool(
                {"documents": [{"id": doc.id}]},
                {"library_path": "/tmp/lib.fichero"},
                MagicMock(),
            )

        written = [row for row in saved if getattr(row, "artifact_type", None) == "dates"]
        assert written, "the tool wrote no dates artifact, so this test proves nothing"
        assert len(emitted) == 1, "one artifact event for the run's artifacts"
        # The event names the artifact that was actually written, not a guess.
        assert emitted[0]["artifact_ids"] == [written[0].id]
        assert emitted[0]["document_ids"] == [doc.id]
