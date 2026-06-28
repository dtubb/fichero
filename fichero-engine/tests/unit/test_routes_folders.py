"""Tests for folder management routes.

Covers virtual folder operations on Workflows, SavedSearches, and Conversations.
Folders are not stored as separate rows — they are derived from folder_path fields
on model instances. SwiftUI uses these routes to render the sidebar folder tree.
"""

from fichero.models import Conversation, SavedSearch, Workflow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workflow(db, name: str, folder_path: str = "/") -> Workflow:
    wf = Workflow(name=name, folder_path=folder_path)
    db.save(wf)
    return wf


def _make_search(db, query: str, folder_path: str = "/") -> SavedSearch:
    ss = SavedSearch(query=query, folder_path=folder_path)
    db.save(ss)
    return ss


def _make_conversation(db, title: str, folder_path: str = "/") -> Conversation:
    cv = Conversation(title=title, folder_path=folder_path)
    db.save(cv)
    return cv


# ---------------------------------------------------------------------------
# list_folders
# ---------------------------------------------------------------------------


class TestListFolders:
    def test_empty_library_returns_no_folders(self, client):
        r = client.get("/api/folders/workflow/folders?parent_path=/")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_root_items_not_returned_as_folders(self, client, db):
        _make_workflow(db, "root-wf", folder_path="/")
        r = client.get("/api/folders/workflow/folders?parent_path=/")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_child_folder_appears_in_listing(self, client, db):
        _make_workflow(db, "archived", folder_path="/archive")
        r = client.get("/api/folders/workflow/folders?parent_path=/")
        assert r.status_code == 200
        paths = [e["path"] for e in r.json()["items"]]
        assert "/archive" in paths

    def test_item_count_is_correct(self, client, db):
        _make_workflow(db, "w1", folder_path="/archive")
        _make_workflow(db, "w2", folder_path="/archive")
        _make_workflow(db, "w3", folder_path="/other")
        r = client.get("/api/folders/workflow/folders?parent_path=/")
        assert r.status_code == 200
        by_path = {e["path"]: e["item_count"] for e in r.json()["items"]}
        assert by_path["/archive"] == 2
        assert by_path["/other"] == 1

    def test_subfolder_not_returned_for_root_query(self, client, db):
        _make_workflow(db, "deep", folder_path="/archive/letters")
        r = client.get("/api/folders/workflow/folders?parent_path=/")
        assert r.status_code == 200
        # Should show /archive, not /archive/letters
        paths = [e["path"] for e in r.json()["items"]]
        assert "/archive" in paths
        assert "/archive/letters" not in paths

    def test_subfolder_returned_for_parent_query(self, client, db):
        _make_workflow(db, "deep", folder_path="/archive/letters")
        r = client.get("/api/folders/workflow/folders?parent_path=/archive")
        assert r.status_code == 200
        paths = [e["path"] for e in r.json()["items"]]
        assert "/archive/letters" in paths

    def test_search_entity_type(self, client, db):
        _make_search(db, "query1", folder_path="/saved")
        r = client.get("/api/folders/search/folders?parent_path=/")
        assert r.status_code == 200
        paths = [e["path"] for e in r.json()["items"]]
        assert "/saved" in paths

    def test_conversation_entity_type(self, client, db):
        _make_conversation(db, "Chat 1", folder_path="/ai-chats")
        r = client.get("/api/folders/conversation/folders?parent_path=/")
        assert r.status_code == 200
        paths = [e["path"] for e in r.json()["items"]]
        assert "/ai-chats" in paths

    def test_parent_path_in_response(self, client, db):
        _make_workflow(db, "wf", folder_path="/archive")
        r = client.get("/api/folders/workflow/folders?parent_path=/")
        assert r.status_code == 200
        entry = r.json()["items"][0]
        assert entry["parent_path"] == "/"


# ---------------------------------------------------------------------------
# create_folder
# ---------------------------------------------------------------------------


class TestCreateFolder:
    def test_create_valid_folder(self, client):
        r = client.post("/api/folders/workflow/folders?folder_path=/projects")
        assert r.status_code == 200
        data = r.json()
        assert data["path"] == "/projects"
        assert data["item_count"] == 0

    def test_create_nested_folder(self, client):
        r = client.post("/api/folders/workflow/folders?folder_path=/archive/letters")
        assert r.status_code == 200
        assert r.json()["path"] == "/archive/letters"

    def test_missing_leading_slash_rejected(self, client):
        r = client.post("/api/folders/workflow/folders?folder_path=noslash")
        assert r.status_code == 400

    def test_trailing_slash_rejected(self, client):
        r = client.post("/api/folders/workflow/folders?folder_path=/bad/")
        assert r.status_code == 400

    def test_item_count_reflects_existing_items(self, client, db):
        _make_workflow(db, "existing", folder_path="/projects")
        r = client.post("/api/folders/workflow/folders?folder_path=/projects")
        assert r.status_code == 200
        assert r.json()["item_count"] == 1


# ---------------------------------------------------------------------------
# rename_folder
# ---------------------------------------------------------------------------


class TestRenameFolder:
    def test_rename_moves_all_items(self, client, db):
        _make_workflow(db, "w1", folder_path="/old")
        _make_workflow(db, "w2", folder_path="/old")
        r = client.put("/api/folders/workflow/folders", json={"old_path": "/old", "new_path": "/new"})
        assert r.status_code == 200
        assert r.json()["moved_count"] == 2
        assert r.json()["new_path"] == "/new"

    def test_rename_updates_subfolders(self, client, db):
        _make_workflow(db, "deep", folder_path="/old/sub")
        r = client.put("/api/folders/workflow/folders", json={"old_path": "/old", "new_path": "/new"})
        assert r.status_code == 200
        assert r.json()["moved_count"] == 1

    def test_rename_no_items_returns_zero(self, client):
        r = client.put(
            "/api/folders/workflow/folders",
            json={"old_path": "/nonexistent", "new_path": "/other"},
        )
        assert r.status_code == 200
        assert r.json()["moved_count"] == 0

    def test_invalid_new_path_rejected(self, client):
        r = client.put(
            "/api/folders/workflow/folders",
            json={"old_path": "/old", "new_path": "no-slash"},
        )
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# move_items
# ---------------------------------------------------------------------------


class TestMoveItems:
    def test_move_single_item(self, client, db):
        wf = _make_workflow(db, "moveme", folder_path="/source")
        r = client.put(
            "/api/folders/workflow/move",
            json={"item_ids": [wf.id], "folder_path": "/destination"},
        )
        assert r.status_code == 200
        assert r.json()["moved_count"] == 1

    def test_move_nonexistent_item_skipped(self, client):
        r = client.put(
            "/api/folders/workflow/move",
            json={"item_ids": ["fake-id"], "folder_path": "/dest"},
        )
        assert r.status_code == 200
        assert r.json()["moved_count"] == 0

    def test_invalid_folder_path_rejected(self, client):
        r = client.put(
            "/api/folders/workflow/move",
            json={"item_ids": [], "folder_path": "no-slash"},
        )
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# delete_folder
# ---------------------------------------------------------------------------


class TestDeleteFolder:
    def test_delete_with_contents_removes_items(self, client, db):
        _make_workflow(db, "w1", folder_path="/to-delete")
        _make_workflow(db, "w2", folder_path="/to-delete")
        r = client.delete(
            "/api/folders/workflow/folders",
            params={"folder_path": "/to-delete", "delete_contents": True},
        )
        assert r.status_code == 200
        assert r.json()["deleted_count"] == 2

    def test_delete_without_contents_moves_to_parent(self, client, db):
        _make_workflow(db, "w1", folder_path="/archive/sub")
        r = client.delete(
            "/api/folders/workflow/folders",
            params={"folder_path": "/archive/sub", "delete_contents": False},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["moved_to_root"] == 1
        assert data["parent_path"] == "/archive"

    def test_delete_empty_folder_returns_zero_counts(self, client):
        r = client.delete(
            "/api/folders/workflow/folders",
            params={"folder_path": "/empty", "delete_contents": False},
        )
        assert r.status_code == 200
        assert r.json()["moved_to_root"] == 0
