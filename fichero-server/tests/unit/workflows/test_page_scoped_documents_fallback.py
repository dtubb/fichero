"""#4298 — a page-scoped run must NEVER widen to the whole PDF.

The vision tools scope per-document: for a single selected page the source
node emits ``files=[parent.pdf]`` paired with ``documents=[page]`` and the
page's ``sequence`` confines the vision pass to that one page. Workflows that
wire only the ``files`` port (older stored copies of presets, hand-built
graphs) lost the pairing — the tool saw a bare PDF path, took the whole-PDF
branch, and processed (and billed) every page.

``documents_from_state_outputs`` recovers the pairing from the upstream
node's recorded outputs in the LangGraph state; these tests pin its contract
and its wiring into transcribe / handwriting / transcribe_review.
"""

from fichero_server.workflows.tools._doc_lookup import documents_from_state_outputs


PAGE_DOC = {
    "id": "page-3",
    "parent_id": "pdf-1",
    "doc_type": "page",
    "sequence": 3,
}


def _state_with_output(node_output):
    return {"outputs": {"files-source": node_output}}


class TestDocumentsFromStateOutputs:
    def test_recovers_page_doc_for_page_scoped_run(self):
        state = _state_with_output(
            {"files": ["/lib/files/a.pdf"], "documents": [PAGE_DOC], "count": 1}
        )
        assert documents_from_state_outputs(state, ["/lib/files/a.pdf"]) == [PAGE_DOC]

    def test_recovers_per_page_fanout_alignment(self):
        pages = [dict(PAGE_DOC, id=f"page-{i}", sequence=i) for i in (1, 2, 3)]
        files = ["/lib/files/a.pdf"] * 3  # parent path repeated per page child
        state = _state_with_output({"files": files, "documents": pages})
        assert documents_from_state_outputs(state, files) == pages

    def test_string_files_input_is_normalised(self):
        state = _state_with_output(
            {"files": ["/lib/files/a.pdf"], "documents": [PAGE_DOC]}
        )
        assert documents_from_state_outputs(state, "/lib/files/a.pdf") == [PAGE_DOC]

    def test_no_match_returns_empty(self):
        state = _state_with_output(
            {"files": ["/lib/files/OTHER.pdf"], "documents": [PAGE_DOC]}
        )
        assert documents_from_state_outputs(state, ["/lib/files/a.pdf"]) == []

    def test_misaligned_lengths_are_rejected(self):
        # A producer whose documents list doesn't pair 1:1 with the files list
        # must not be trusted — wrong pairing routes artifacts to the wrong
        # documents (#2430 class).
        state = _state_with_output(
            {"files": ["/lib/files/a.pdf"], "documents": [PAGE_DOC, PAGE_DOC]}
        )
        assert documents_from_state_outputs(state, ["/lib/files/a.pdf"]) == []

    def test_empty_files_and_malformed_state_are_safe(self):
        assert documents_from_state_outputs({"outputs": {}}, []) == []
        assert documents_from_state_outputs({}, ["/a.pdf"]) == []
        assert documents_from_state_outputs({"outputs": None}, ["/a.pdf"]) == []
        assert (
            documents_from_state_outputs({"outputs": {"n": "not-a-dict"}}, ["/a.pdf"])
            == []
        )


class TestVisionToolsUseTheFallback:
    """The three paleography-relevant vision tools must consult the fallback
    when their `documents` input port is unwired."""

    def test_tools_wire_the_fallback(self):
        import inspect

        from fichero_server.workflows.tools import (
            handwriting,
            transcribe,
            transcribe_review,
        )

        for module, fn_name in (
            (transcribe, "transcribe"),
            (handwriting, "handwriting"),
            (transcribe_review, "transcribe_review"),
        ):
            source = inspect.getsource(module)
            assert "documents_from_state_outputs" in source, (
                f"{fn_name} must recover aligned documents when the "
                "documents port is unwired (#4298)"
            )
