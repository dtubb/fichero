"""One selected file must never run on the whole folder (#4523 #4396).

Every client surface sends exactly the selected ids, and the engine then let
each of the four source tools decide independently whether to honor them:
`files` yes, `selection` yes, `collection` yes-via-bolt-on, `folder` NO.
`folder_tool` never read `selected_doc_ids` at all, so a workflow authored
with a folder source ran on every file in the configured folder even when the
request carried an explicit one-file selection — burning real provider money
on documents the user never pointed at.

The class fix: the selection is resolved ONCE, by `_resolve_selection_pairs`,
and every source tool reads that resolved set when a selection is present.
The resolver enforces both scope invariants:

* lower bound (#4467): a selection resolving to nothing raises;
* upper bound (#4523): every resolved work unit must descend from a selected
  id — the engine raises rather than silently widening.

Nothing here calls a model.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fichero_server.models import Document, DocType
from fichero_server.workflows.tools.sources import (
    _assert_selection_upper_bound,
    _resolve_selection_pairs,
    collection_tool,
    files_tool,
    folder_tool,
)


def _file(doc_id: str, parent_id: str | None = None) -> Document:
    return Document(
        id=doc_id,
        name=f"{doc_id}.jpg",
        path=f"/lib/files/{doc_id}.jpg",
        doc_type=DocType.file,
        parent_id=parent_id,
    )


def _folder(doc_id: str) -> Document:
    return Document(id=doc_id, name=doc_id, path=None, doc_type=DocType.folder)


def _db_with(docs: list[Document]) -> MagicMock:
    """A mock db: `get` by id, `query` by parent_id (ignoring doc_type filters
    except pages, which this fixture never has)."""
    by_id = {d.id: d for d in docs}
    db = MagicMock()
    db.get.side_effect = lambda cls, doc_id: by_id.get(doc_id)

    def query(cls, **kwargs):
        parent_id = kwargs.get("parent_id")
        if kwargs.get("doc_type") == DocType.page:
            return []
        return [d for d in docs if d.parent_id == parent_id]

    db.query.side_effect = query
    return db


# ---------------------------------------------------------------------------
# The reported defect: folder_tool ignored the selection entirely
# ---------------------------------------------------------------------------


class TestFolderToolHonorsTheSelection:
    @pytest.mark.asyncio
    async def test_one_selected_file_in_a_folder_of_five_runs_on_one(self):
        """The #4523 incident shape: folder source configured for a folder of
        five, request selects ONE file — the run must touch exactly that
        file, and the folder must never even be enumerated."""
        folder = _folder("folder-x")
        members = [_file(f"file-{i}", parent_id="folder-x") for i in range(5)]
        db = _db_with([folder, *members])

        with patch("fichero_server.workflows.tools.sources.db_manager") as mgr, \
             patch(
                 "fichero_server.workflows.tools.sources._load_capped_folder_files"
             ) as load_folder:
            mgr.get_database.return_value = db
            result = await folder_tool(
                inputs={"folder_id": "folder-x"},
                state={"library_path": "/lib", "selected_doc_ids": ["file-2"]},
                llm_config=MagicMock(),
            )

        assert result["count"] == 1, (
            f"a selection of 1 in a folder of 5 resolved to {result['count']} "
            "— folder_tool is still ignoring selected_doc_ids (#4523)"
        )
        assert [d["id"] for d in result["documents"]] == ["file-2"]
        assert load_folder.call_count == 0, (
            "the configured folder was enumerated despite an explicit "
            "selection — the widening is one refactor away from returning"
        )

    @pytest.mark.asyncio
    async def test_selection_override_does_not_claim_the_folder(self):
        """Honesty at the seam (#4404): the node did not read the configured
        folder, so it must not report having done so, nor fan out over the
        folder's subfolders."""
        db = _db_with([_file("file-a")])
        with patch("fichero_server.workflows.tools.sources.db_manager") as mgr:
            mgr.get_database.return_value = db
            result = await folder_tool(
                inputs={"folder_id": "folder-x"},
                state={"library_path": "/lib", "selected_doc_ids": ["file-a"]},
                llm_config=MagicMock(),
            )
        assert not result.get("folder_id")
        assert result.get("subfolders") == []

    @pytest.mark.asyncio
    async def test_no_selection_still_lists_the_configured_folder(self):
        """The authored config applies when no selection was sent — the fix
        must not break folder-source workflows run without a selection."""
        members = [_file(f"file-{i}", parent_id="folder-x") for i in range(3)]
        db = _db_with(members)
        with patch("fichero_server.workflows.tools.sources.db_manager") as mgr, \
             patch(
                 "fichero_server.workflows.tools.sources._load_capped_folder_files",
                 return_value=members,
             ):
            mgr.get_database.return_value = db
            result = await folder_tool(
                inputs={"folder_id": "folder-x"},
                state={"library_path": "/lib"},
                llm_config=MagicMock(),
            )
        assert result["count"] == 3
        assert result["folder_id"] == "folder-x"

    @pytest.mark.asyncio
    async def test_stale_selection_refuses_rather_than_widening(self):
        """#4467's lower bound now holds at the folder source too: a selection
        of ids the library no longer has must raise, not fall back to running
        the whole configured folder."""
        members = [_file(f"file-{i}", parent_id="folder-x") for i in range(3)]
        db = _db_with(members)
        with patch("fichero_server.workflows.tools.sources.db_manager") as mgr:
            mgr.get_database.return_value = db
            with pytest.raises(ValueError, match="resolved to 0 processable files"):
                await folder_tool(
                    inputs={"folder_id": "folder-x"},
                    state={
                        "library_path": "/lib",
                        "selected_doc_ids": ["deleted-doc"],
                    },
                    llm_config=MagicMock(),
                )


# ---------------------------------------------------------------------------
# The other tools ride the same resolver
# ---------------------------------------------------------------------------


class TestEverySourceToolResolvesTheSameSelection:
    @pytest.mark.asyncio
    async def test_files_tool_selection_of_one_never_becomes_the_folder(self):
        folder = _folder("folder-x")
        members = [_file(f"file-{i}", parent_id="folder-x") for i in range(5)]
        db = _db_with([folder, *members])
        with patch("fichero_server.workflows.tools.sources.db_manager") as mgr:
            mgr.get_database.return_value = db
            result = await files_tool(
                inputs={},
                state={"library_path": "/lib", "selected_doc_ids": ["file-0"]},
                llm_config=MagicMock(),
            )
        assert result["count"] == 1
        assert [d["id"] for d in result["documents"]] == ["file-0"]

    @pytest.mark.asyncio
    async def test_collection_tool_selection_now_expands_folders(self):
        """The deleted bolt-on never expanded a selected folder (it silently
        dropped it: no path, no parent). The shared resolver does — deleting
        the bolt-on made collection strictly more correct."""
        folder = _folder("folder-y")
        members = [_file(f"m-{i}", parent_id="folder-y") for i in range(2)]
        db = _db_with([folder, *members])
        with patch("fichero_server.workflows.tools.sources.db_manager") as mgr:
            mgr.get_database.return_value = db
            result = await collection_tool(
                inputs={"collection_id": "some-collection"},
                state={"library_path": "/lib", "selected_doc_ids": ["folder-y"]},
                llm_config=MagicMock(),
            )
        assert result["count"] == 2
        assert {d["id"] for d in result["documents"]} == {"m-0", "m-1"}

    @pytest.mark.asyncio
    async def test_collection_tool_stale_selection_refuses(self):
        db = _db_with([])
        with patch("fichero_server.workflows.tools.sources.db_manager") as mgr:
            mgr.get_database.return_value = db
            with pytest.raises(ValueError, match="resolved to 0 processable files"):
                await collection_tool(
                    inputs={"collection_id": "col"},
                    state={"library_path": "/lib", "selected_doc_ids": ["gone"]},
                    llm_config=MagicMock(),
                )


# ---------------------------------------------------------------------------
# The invariants themselves
# ---------------------------------------------------------------------------


class TestTheScopeInvariants:
    def test_resolver_output_equals_the_selection_for_leaf_files(self):
        docs = [_file("a"), _file("b")]
        db = _db_with(docs)
        pairs = _resolve_selection_pairs(db, ["a", "b"], "/lib")
        assert [d.id for _, d in pairs] == ["a", "b"], (
            "for a leaf-file selection the resolved set must EQUAL the "
            "selection — nothing added, nothing dropped"
        )

    def test_upper_bound_raises_on_a_widened_set(self):
        """The guard must FIRE: a resolved document whose origin is not in
        the selection is exactly the #4396 widening, and it must raise, never
        pass through (guardrails-must-match-granularity)."""
        stranger = _file("stranger")
        with pytest.raises(ValueError, match="scope invariant violated"):
            _assert_selection_upper_bound(
                [("file-1", _file("file-1")), ("not-selected", stranger)],
                ["file-1"],
            )

    def test_upper_bound_passes_descendants_of_a_selected_container(self):
        child = _file("child", parent_id="folder-x")
        assert _assert_selection_upper_bound([("folder-x", child)], ["folder-x"]) is None

    def test_empty_resolution_raises_before_the_upper_bound(self):
        db = _db_with([])
        with pytest.raises(ValueError, match="resolved to 0 processable files"):
            _resolve_selection_pairs(db, ["gone-1", "gone-2"], "/lib")
