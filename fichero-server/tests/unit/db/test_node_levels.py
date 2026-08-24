"""Which tier of the tree a caller gets.

Fixtures mirror the REAL shape measured in Marshall Diaries v3 on 2026-08-22:
one diary folder holding 75 openings (each with 2 parts) plus 4 whole pages
that were never split. The whole pages are the adversarial case — a naive
"replace containers with their children" drops every page that has no
container, and 62 of them vanish from the 1915 folder.
"""

from __future__ import annotations

import pytest

from fichero_server.db.node_levels import (
    NodeLevel,
    resolve_level,
    resolve_workflow_targets,
)
from fichero_server.models import Document
from fichero_server.models.knowledge import (
    ClassificationDimension,
    ClassificationValue,
)


@pytest.fixture
def tree(db):
    """A folder holding 2 openings (2 parts each) and 1 whole page."""
    folder = Document(name="NCM_Diary_1926", doc_type="folder")
    db.save(folder)

    made = {"folder": folder, "openings": [], "parts": [], "whole": None}
    for index in (1, 2):
        opening = Document(
            name=f"IMG_{index:03d}", parent_id=folder.id,
            prototype_key="opening", sequence=index,
        )
        db.save(opening)
        made["openings"].append(opening)
        for part in (1, 2):
            child = Document(
                name=f"IMG_{index:03d}_part_{part}", parent_id=opening.id,
                prototype_key="page", sequence=part,
            )
            db.save(child)
            made["parts"].append(child)

    whole = Document(
        name="IMG_009", parent_id=folder.id, prototype_key="page", sequence=9
    )
    db.save(whole)
    made["whole"] = whole
    return made


def _children_of(db):
    def fetch(doc: Document) -> list[Document]:
        return list(db.query(Document, parent_id=doc.id))
    return fetch


def _stored(db, tree):
    return list(db.query(Document, parent_id=tree["folder"].id))


class TestStoredLevel:
    def test_stored_returns_the_tree_as_held(self, db, tree):
        """Openings AND whole pages side by side — which is correct, and is
        what Daniel was seeing without a way to choose."""
        out = resolve_level(db, _stored(db, tree), NodeLevel.stored)
        assert sorted(d.name for d in out) == ["IMG_001", "IMG_002", "IMG_009"]

    def test_stored_is_the_default(self, db, tree):
        """Adding the parameter must change nothing for existing callers."""
        assert [d.id for d in resolve_level(db, _stored(db, tree))] == [
            d.id for d in _stored(db, tree)
        ]


class TestContentLevel:
    def test_openings_resolve_to_their_pages(self, db, tree):
        out = resolve_level(
            db, _stored(db, tree), NodeLevel.content, children_of=_children_of(db)
        )
        assert sorted(d.name for d in out if "part" in d.name) == [
            "IMG_001_part_1", "IMG_001_part_2",
            "IMG_002_part_1", "IMG_002_part_2",
        ]

    def test_the_whole_page_SURVIVES(self, db, tree):
        """The adversarial case. A page that was never split has no container
        to look through; dropping it would lose 62 pages from the real 1915
        folder."""
        out = resolve_level(
            db, _stored(db, tree), NodeLevel.content, children_of=_children_of(db)
        )
        assert "IMG_009" in {d.name for d in out}

    def test_count_is_parts_plus_unsplit(self, db, tree):
        out = resolve_level(
            db, _stored(db, tree), NodeLevel.content, children_of=_children_of(db)
        )
        assert len(out) == 5  # 2 openings x 2 parts, plus the 1 whole page

    def test_parts_come_back_in_reading_order(self, db, tree):
        out = resolve_level(
            db, _stored(db, tree), NodeLevel.content, children_of=_children_of(db)
        )
        first = [d.name for d in out if d.name.startswith("IMG_001")]
        assert first == ["IMG_001_part_1", "IMG_001_part_2"]

    def test_containers_are_replaced_in_place(self, db, tree):
        """Expanding must not re-sort the folder into a different sequence
        than the user was just looking at."""
        out = [d.name for d in resolve_level(
            db, _stored(db, tree), NodeLevel.content, children_of=_children_of(db)
        )]
        assert out.index("IMG_001_part_1") < out.index("IMG_002_part_1")


class TestRefusals:
    def test_a_childless_container_returns_ITSELF(self, db):
        """An opening whose parts failed to import is still a real page
        someone can open. Dropping it would be the library lying about what
        it holds."""
        folder = Document(name="f", doc_type="folder")
        db.save(folder)
        lonely = Document(name="orphan_opening", parent_id=folder.id, prototype_key="opening")
        db.save(lonely)

        out = resolve_level(
            db, [lonely], NodeLevel.content, children_of=lambda d: []
        )
        assert [d.name for d in out] == ["orphan_opening"]

    def test_unknown_prototype_leaves_the_node_visible(self, db):
        """An unresolvable prototype must not decide a node is a container.
        The safe failure is showing a spread where a page was wanted — never
        a page disappearing."""
        doc = Document(name="mystery", prototype_key="not_a_real_prototype")
        db.save(doc)

        out = resolve_level(db, [doc], NodeLevel.content, children_of=lambda d: [])
        assert [d.name for d in out] == ["mystery"]

    def test_node_without_a_prototype_passes_through(self, db):
        doc = Document(name="plain")
        db.save(doc)
        out = resolve_level(db, [doc], NodeLevel.content, children_of=lambda d: [])
        assert [d.name for d in out] == ["plain"]

    def test_deleted_children_are_not_resurrected(self, db, tree):
        """Unsplit soft-deletes the parts. Expanding an unsplit opening must
        not bring them back."""
        for part in tree["parts"]:
            part.deleted_at = part.updated_at
            db.save(part)

        out = resolve_level(
            db, _stored(db, tree), NodeLevel.content, children_of=_children_of(db)
        )
        # Both openings come back as THEMSELVES, plus the whole page.
        assert sorted(d.name for d in out) == ["IMG_001", "IMG_002", "IMG_009"]


class TestPrototypeDriven:
    def test_a_new_container_kind_needs_no_code_change(self, db):
        """The attribute decides, not a hard-coded 'opening'. A gatefold or a
        photographed object with detail shots gets this by declaring it."""
        db.save(ClassificationValue(
            dimension=ClassificationDimension.document_prototype,
            key="gatefold", label="Gatefold",
            attributes={"prefer_children_in_library": True},
        ))
        parent = Document(name="plate", prototype_key="gatefold")
        db.save(parent)
        leaf = Document(name="panel", parent_id=parent.id, sequence=1)
        db.save(leaf)

        out = resolve_level(
            db, [parent], NodeLevel.content, children_of=_children_of(db)
        )
        assert [d.name for d in out] == ["panel"]

    def test_a_prototype_without_the_attribute_is_not_a_container(self, db):
        db.save(ClassificationValue(
            dimension=ClassificationDimension.document_prototype,
            key="letter_page", label="Letter Page", attributes={},
        ))
        doc = Document(name="p1", prototype_key="letter_page")
        db.save(doc)

        out = resolve_level(db, [doc], NodeLevel.content, children_of=lambda d: [])
        assert [d.name for d in out] == ["p1"]


class TestWorkflowTargets:
    """A container is never a unit of work.

    This is the regression that produced Marshall v3's state: the library
    showed openings, the user selected what the library showed, and every
    diary entry was extracted from a SPREAD transcript and anchored to a
    spread frame while the pages' own transcripts sat unread. Nothing was
    broken — the workflow correctly processed the documents it was handed.
    """

    def test_a_mixed_folder_run_hits_pages_and_NO_openings(self, db, tree):
        """The manager's acceptance condition, on the real folder shape."""
        selection = [{"id": d.id} for d in _stored(db, tree)]

        targets = resolve_workflow_targets(db, selection)

        names = {d.name for d in targets}
        assert names == {
            "IMG_001_part_1", "IMG_001_part_2",
            "IMG_002_part_1", "IMG_002_part_2",
            "IMG_009",
        }
        assert not any(d.prototype_key == "opening" for d in targets)

    def test_the_unsplit_page_is_still_processed(self, db, tree):
        """62 pages in the real 1915 folder have no opening. A resolver that
        only expanded containers would never run on them."""
        targets = resolve_workflow_targets(db, [{"id": tree["whole"].id}])
        assert [d.name for d in targets] == ["IMG_009"]

    def test_selecting_an_opening_directly_still_yields_its_pages(self, db, tree):
        """What actually happened in v3 — the user selected spreads because
        that is what the grid offered."""
        targets = resolve_workflow_targets(db, [{"id": tree["openings"][0].id}])
        assert [d.name for d in targets] == ["IMG_001_part_1", "IMG_001_part_2"]

    def test_accepts_bare_ids_and_documents_too(self, db, tree):
        """Tools are handed whatever the runtime put in inputs['documents'];
        a resolver that accepted only dicts would pass the rest through
        unresolved, which is the silent version of the original bug."""
        by_dict = resolve_workflow_targets(db, [{"id": tree["openings"][0].id}])
        by_id = resolve_workflow_targets(db, [tree["openings"][0].id])
        by_doc = resolve_workflow_targets(db, [tree["openings"][0]])
        assert [d.id for d in by_dict] == [d.id for d in by_id] == [d.id for d in by_doc]

    def test_unknown_ids_are_skipped_not_fatal(self, db, tree):
        targets = resolve_workflow_targets(
            db, [{"id": "does-not-exist"}, {"id": tree["whole"].id}]
        )
        assert [d.name for d in targets] == ["IMG_009"]

    def test_empty_selection_is_empty(self, db):
        assert resolve_workflow_targets(db, []) == []
