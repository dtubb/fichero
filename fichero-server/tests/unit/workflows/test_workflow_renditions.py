"""Image workflows must persist their pixels, not just return temp paths.

The bug this covers, found live by Daniel on 2026-08-21:
`remove_background_images` did real per-file work, wrote PNGs to
`$TMPDIR/fichero-background-removed-images`, returned the paths — and NOTHING
persisted. No artifact, no rendition, no document change. The run reported
success in ~1ms with no user-visible effect.
"""

from __future__ import annotations

from pathlib import Path

from fichero_server.models import Document, Rendition
from fichero_server.workflows.tools.image_edit_chains import (
    describe_no_effect,
    persist_workflow_renditions,
)


def _doc(db, tmp_path, name="IMG_001.jpg") -> tuple[Document, Path]:
    source = tmp_path / name
    source.write_bytes(b"\xff\xd8original")
    doc = Document(name=name, path=str(source), metadata={"source_path": str(source)})
    db.save(doc)
    return doc, source


def _output(tmp_path, name="IMG_001.png") -> Path:
    out = tmp_path / "derived" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"\x89PNGderived")
    return out


class TestPersistence:
    def test_output_becomes_a_rendition_on_its_document(self, db, tmp_path, test_package):
        doc, source = _doc(db, tmp_path)
        out = _output(tmp_path)

        report = persist_workflow_renditions(
            {"documents": [{"id": doc.id}], "library_path": str(test_package)},
            {},
            role="background_removed",
            results=[{"source": str(source), "outputs": [str(out)]}],
        )

        rows = db.query(Rendition, document_id=doc.id)
        assert len(report["renditions"]) == 1
        assert [r.role for r in rows] == ["background_removed"]

    def test_bytes_are_copied_out_of_the_temp_directory(self, db, tmp_path, test_package):
        """A Rendition row pointing into $TMPDIR is a promise the library
        cannot keep — temp dirs are swept."""
        doc, source = _doc(db, tmp_path)
        out = _output(tmp_path)

        persist_workflow_renditions(
            {"documents": [{"id": doc.id}], "library_path": str(test_package)},
            {},
            role="enhanced",
            results=[{"source": str(source), "outputs": [str(out)]}],
        )

        stored = Path(db.query(Rendition, document_id=doc.id)[0].path)
        assert stored != out
        assert stored.is_file()
        assert stored.read_bytes() == b"\x89PNGderived"

    def test_a_workflow_rendition_is_never_primary(self, db, tmp_path, test_package):
        """A pass must not silently change what the reader opens on — that is
        how someone ends up reading an enhanced crop believing it is the
        archival scan."""
        doc, source = _doc(db, tmp_path)

        persist_workflow_renditions(
            {"documents": [{"id": doc.id}], "library_path": str(test_package)},
            {},
            role="enhanced",
            results=[{"source": str(source), "outputs": [str(_output(tmp_path))]}],
        )

        assert db.query(Rendition, document_id=doc.id)[0].is_primary is False

    def test_rerun_does_not_stack_duplicate_rows(self, db, tmp_path, test_package):
        doc, source = _doc(db, tmp_path)
        args = (
            {"documents": [{"id": doc.id}], "library_path": str(test_package)},
            {},
        )
        results = [{"source": str(source), "outputs": [str(_output(tmp_path))]}]

        persist_workflow_renditions(*args, role="enhanced", results=results)
        second = persist_workflow_renditions(*args, role="enhanced", results=results)

        assert second["renditions"] == []
        assert len(db.query(Rendition, document_id=doc.id)) == 1


class TestPairing:
    def test_outputs_pair_by_source_path_not_list_position(self, db, tmp_path, test_package):
        """Index-pairing mis-attributes every output the moment one file fails
        or is skipped — and a rendition on the wrong page is exactly the
        defect this program exists to remove."""
        first, first_src = _doc(db, tmp_path, "A.jpg")
        second, second_src = _doc(db, tmp_path, "B.jpg")
        out_b = _output(tmp_path, "B.png")

        persist_workflow_renditions(
            {
                "documents": [{"id": first.id}, {"id": second.id}],
                "library_path": str(test_package),
            },
            {},
            role="enhanced",
            # A failed for its own reasons; only B produced output. Position 0
            # is B, which index-pairing would hang on document A.
            results=[{"source": str(second_src), "outputs": [str(out_b)]}],
        )

        assert db.query(Rendition, document_id=first.id) == []
        assert len(db.query(Rendition, document_id=second.id)) == 1

    def test_document_matched_via_metadata_source_path(self, db, tmp_path, test_package):
        """LINK imports record the original location while COPY records the
        library one; a workflow may have been handed either."""
        source = tmp_path / "linked.jpg"
        source.write_bytes(b"x")
        doc = Document(name="linked.jpg", path="/library/copy.jpg",
                       metadata={"source_path": str(source)})
        db.save(doc)

        persist_workflow_renditions(
            {"documents": [{"id": doc.id}], "library_path": str(test_package)},
            {},
            role="enhanced",
            results=[{"source": str(source), "outputs": [str(_output(tmp_path))]}],
        )

        assert len(db.query(Rendition, document_id=doc.id)) == 1

    def test_unmatchable_output_is_recorded_never_guessed(self, db, tmp_path, test_package):
        """The output exists but we cannot say WHICH node it belongs to.
        Attaching it to a guess would be the original defect."""
        doc, _ = _doc(db, tmp_path)
        out = _output(tmp_path)

        report = persist_workflow_renditions(
            {"documents": [{"id": doc.id}], "library_path": str(test_package)},
            {},
            role="enhanced",
            results=[{"source": "/somewhere/never/imported.jpg", "outputs": [str(out)]}],
        )

        assert report["renditions"] == []
        assert report["skipped_no_document"] == 1
        assert str(out) in report["unmatched_outputs"]
        assert db.query(Rendition, document_id=doc.id) == []

    def test_no_library_in_scope_is_reported_not_silent(self, db, tmp_path):
        """Pipeline-only runs never touch a library. That is fine — but it is
        STATED, so the caller does not infer it from an empty list."""
        report = persist_workflow_renditions(
            {}, {}, role="enhanced",
            results=[{"source": "/a.jpg", "outputs": ["/b.png"]}],
        )

        assert report["renditions"] == []
        assert "no library_path" in report["skipped_reason"]


class TestNoEffectReporting:
    """A green tick on a run that changed nothing is worse than an error,
    because nobody investigates a success."""

    def test_no_inputs(self):
        assert describe_no_effect([], [], {}) == "no input files were supplied — nothing to do"

    def test_inputs_but_no_outputs(self):
        assert "produced no output" in describe_no_effect(["a.jpg"], [], {})

    def test_outputs_but_nothing_persisted(self):
        message = describe_no_effect(["a.jpg"], ["a.png"], {})
        assert "no rendition was attached" in message

    def test_outputs_but_no_library(self):
        message = describe_no_effect(["a.jpg"], ["a.png"], {"skipped_reason": "no library_path in scope"})
        assert "not persisted" in message and "no library_path" in message

    def test_outputs_unmatched_says_how_many(self):
        message = describe_no_effect(["a.jpg"], ["a.png"], {"skipped_no_document": 2})
        assert "2 could not be matched" in message

    def test_success_reports_nothing(self):
        assert describe_no_effect(["a.jpg"], ["a.png"], {"renditions": [{"document_id": "d"}]}) is None
