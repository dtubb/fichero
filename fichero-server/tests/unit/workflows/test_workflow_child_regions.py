"""split_images / segment_images must create NODES, not just files.

Same disease remove_background had: real pixel work, part files written to a
temp directory, paths returned — and no node, no geometry, no user-visible
effect. The run reports success and the library is unchanged.

The convergence is the point. Children carry `region_in_parent`, the same
geometry the in-app split writes since ca1ed6b25, so a page cut by a workflow
and a page cut by hand are ONE shape — one library view, one unsplit, one set
of coordinate maths.
"""

from __future__ import annotations

from pathlib import Path

from fichero_server.models import Document, Rendition
from fichero_server.models.anchors import RegionConfidence
from fichero_server.workflows.tools.image_edit_chains import (
    _region_from_part,
    persist_workflow_child_regions,
)


def _parent(db, tmp_path, name="opening.jpg") -> tuple[Document, Path]:
    source = tmp_path / name
    source.write_bytes(b"\xff\xd8opening")
    doc = Document(name=name, path=str(source), metadata={"source_path": str(source)})
    db.save(doc)
    return doc, source


def _part_file(tmp_path, name) -> Path:
    out = tmp_path / "parts" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"\x89PNG" + name.encode())
    return out


def _halves(tmp_path) -> list[dict]:
    return [
        {"part": 1, "bbox": [0, 0, 200, 400], "source_size": [400, 400],
         "output_file": str(_part_file(tmp_path, "p1.png"))},
        {"part": 2, "bbox": [200, 0, 200, 400], "source_size": [400, 400],
         "output_file": str(_part_file(tmp_path, "p2.png"))},
    ]


class TestRegionFromPart:
    def test_left_half(self):
        region = _region_from_part(
            {"bbox": [0, 0, 200, 400], "source_size": [400, 400]}, "workflow-split"
        )
        assert region.rect == [0.0, 0.0, 0.5, 1.0]

    def test_confidence_is_measured(self):
        """A workflow CUT the pixels at these coordinates — it is not a
        nominal guess at where a fold might be."""
        region = _region_from_part(
            {"bbox": [0, 0, 10, 10], "source_size": [100, 100]}, "workflow-split"
        )
        assert region.confidence is RegionConfidence.measured

    def test_missing_source_size_yields_no_region(self):
        """A rect against an unrecorded frame is the defect this program
        removes — better absent than guessed."""
        assert _region_from_part({"bbox": [0, 0, 10, 10]}, "workflow-split") is None

    def test_zero_sized_frame_yields_no_region(self):
        assert _region_from_part(
            {"bbox": [0, 0, 10, 10], "source_size": [0, 0]}, "workflow-split"
        ) is None

    def test_degenerate_bbox_yields_no_region(self):
        assert _region_from_part(
            {"bbox": [0, 0, 0, 10], "source_size": [100, 100]}, "workflow-split"
        ) is None


class TestChildCreation:
    def test_parts_become_children_of_their_source(self, db, tmp_path, test_package):
        parent, source = _parent(db, tmp_path)

        report = persist_workflow_child_regions(
            {"documents": [{"id": parent.id}], "library_path": str(test_package)},
            {},
            results=[{"source": str(source), "parts": _halves(tmp_path)}],
            part_key="parts", role="split_part", method="workflow-split", name="part",
        )

        children = db.query(Document, parent_id=parent.id)
        assert len(report["children"]) == 2
        assert len(children) == 2

    def test_children_carry_the_converged_geometry(self, db, tmp_path, test_package):
        parent, source = _parent(db, tmp_path)

        persist_workflow_child_regions(
            {"documents": [{"id": parent.id}], "library_path": str(test_package)},
            {},
            results=[{"source": str(source), "parts": _halves(tmp_path)}],
            part_key="parts", role="split_part", method="workflow-split", name="part",
        )

        regions = sorted(
            (db.get(Document, c.id).region_in_parent.rect
             for c in db.query(Document, parent_id=parent.id)),
            key=lambda r: r[0],
        )
        assert regions == [[0.0, 0.0, 0.5, 1.0], [0.5, 0.0, 0.5, 1.0]]

    def test_each_child_gets_its_own_rendition(self, db, tmp_path, test_package):
        """A workflow part HAS bytes, unlike an in-app split child which is a
        virtual region of its parent. The converged model allows both."""
        parent, source = _parent(db, tmp_path)

        persist_workflow_child_regions(
            {"documents": [{"id": parent.id}], "library_path": str(test_package)},
            {},
            results=[{"source": str(source), "parts": _halves(tmp_path)[:1]}],
            part_key="parts", role="split_part", method="workflow-split", name="part",
        )

        child = db.query(Document, parent_id=parent.id)[0]
        rows = db.query(Rendition, document_id=child.id)
        assert [r.role for r in rows] == ["split_part"]
        assert rows[0].is_primary is True

    def test_bytes_leave_the_temp_directory(self, db, tmp_path, test_package):
        parent, source = _parent(db, tmp_path)
        parts = _halves(tmp_path)[:1]

        persist_workflow_child_regions(
            {"documents": [{"id": parent.id}], "library_path": str(test_package)},
            {},
            results=[{"source": str(source), "parts": parts}],
            part_key="parts", role="split_part", method="workflow-split", name="part",
        )

        child = db.query(Document, parent_id=parent.id)[0]
        assert Path(child.path) != Path(parts[0]["output_file"])
        assert Path(child.path).is_file()

    def test_children_are_discoverable_by_the_unsplit_key(self, db, tmp_path, test_package):
        """Same `split_source_id` the in-app split uses, so `_split_children`
        — and therefore the audited, undoable unsplit — finds these too."""
        parent, source = _parent(db, tmp_path)

        persist_workflow_child_regions(
            {"documents": [{"id": parent.id}], "library_path": str(test_package)},
            {},
            results=[{"source": str(source), "parts": _halves(tmp_path)}],
            part_key="parts", role="split_part", method="workflow-split", name="part",
        )

        children = db.query(Document, parent_id=parent.id)
        assert all((c.metadata or {})["split_source_id"] == parent.id for c in children)


class TestRefusalsAndIdempotence:
    def test_rerun_creates_no_duplicate_children(self, db, tmp_path, test_package):
        parent, source = _parent(db, tmp_path)
        args = (
            {"documents": [{"id": parent.id}], "library_path": str(test_package)},
            {},
        )
        results = [{"source": str(source), "parts": _halves(tmp_path)}]
        kwargs = dict(part_key="parts", role="split_part",
                      method="workflow-split", name="part")

        persist_workflow_child_regions(*args, results=results, **kwargs)
        second = persist_workflow_child_regions(*args, results=results, **kwargs)

        assert second["children"] == []
        assert len(db.query(Document, parent_id=parent.id)) == 2

    def test_unmatched_source_creates_nothing(self, db, tmp_path, test_package):
        parent, _ = _parent(db, tmp_path)

        report = persist_workflow_child_regions(
            {"documents": [{"id": parent.id}], "library_path": str(test_package)},
            {},
            results=[{"source": "/never/imported.jpg", "parts": _halves(tmp_path)}],
            part_key="parts", role="split_part", method="workflow-split", name="part",
        )

        assert report["children"] == []
        assert "/never/imported.jpg" in report["unmatched_sources"]
        assert db.query(Document, parent_id=parent.id) == []

    def test_part_without_a_frame_still_becomes_a_child_but_no_region(
        self, db, tmp_path, test_package
    ):
        """Losing the node would lose the pixels; guessing the region would be
        the original defect. So: child yes, region no, counted."""
        parent, source = _parent(db, tmp_path)
        part = {"part": 1, "bbox": [0, 0, 200, 400],
                "output_file": str(_part_file(tmp_path, "noframe.png"))}

        report = persist_workflow_child_regions(
            {"documents": [{"id": parent.id}], "library_path": str(test_package)},
            {},
            results=[{"source": str(source), "parts": [part]}],
            part_key="parts", role="split_part", method="workflow-split", name="part",
        )

        assert report["skipped_no_region"] == 1
        child = db.query(Document, parent_id=parent.id)[0]
        assert child.region_in_parent is None

    def test_no_library_in_scope_is_reported(self, db, tmp_path):
        report = persist_workflow_child_regions(
            {}, {}, results=[{"source": "/a.jpg", "parts": _halves(tmp_path)}],
            part_key="parts", role="split_part", method="workflow-split", name="part",
        )

        assert report["children"] == []
        assert "no library_path" in report["skipped_reason"]

    def test_no_archival_original_is_attached(self, db, tmp_path, test_package):
        """The backfill scope decision is parked with Daniel; a workflow must
        not pre-empt it by attaching originals of its own accord."""
        parent, source = _parent(db, tmp_path)

        persist_workflow_child_regions(
            {"documents": [{"id": parent.id}], "library_path": str(test_package)},
            {},
            results=[{"source": str(source), "parts": _halves(tmp_path)}],
            part_key="parts", role="split_part", method="workflow-split", name="part",
        )

        assert db.query(Rendition, document_id=parent.id) == []
