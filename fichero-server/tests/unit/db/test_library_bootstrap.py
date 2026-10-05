"""A library is bootstrapped with ONE thing in it: its Sources folder (#5413).

Ruling 2026-08-31: there is no default Inbox. ``db/library_bootstrap.py`` (which held
``INBOX_NAME`` and ``ensure_inbox_folder``) is deleted along with every path that called it:
nothing in the app or the engine creates an Inbox any more.

Ruling 2026-10-04 (#5413, ``sidebar.project.has-a-sources-folder``) adds exactly one folder
back, for a different reason: Sources is where an import that names no folder lands, so the
engine makes it on a project's first open. It is NOT the Inbox it replaces in one way that
matters, pinned below: the open makes it once and never re-makes it after a person deletes it
(the Inbox came back on every open). Anything else in the project is left alone.

A root folder named "Inbox" is still ordinary user content. It has no guard
(delete/move/rename all work, like any folder the user made); the only thing
that still knows the name is the Swift root-drop routing, which files loose
drops into one the USER made, and the sidebar, which hoists it.
"""

import pytest

from fichero_server.models import DocType, Document


@pytest.fixture(autouse=True)
def _open_like_the_app(monkeypatch):
    """The open as it runs in the app: no workflow presets, no derivative resume, Sources ON."""
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    monkeypatch.setenv("FICHERO_SKIP_DERIVATIVE_RESUME", "1")
    monkeypatch.delenv("FICHERO_SKIP_SOURCES_FOLDER", raising=False)


def test_a_new_library_is_bootstrapped_with_only_its_sources_folder(tmp_path):
    """No Inbox, nothing else -- `get_database` seeds the Sources folder and no other document."""
    from fichero_server.db.manager import DatabaseManager

    package = tmp_path / "Fresh.fichero"
    package.mkdir()
    manager = DatabaseManager()
    db = manager.get_database(package)
    try:
        docs = list(db.query(Document))
        assert [(d.name, d.doc_type, d.parent_id) for d in docs] == [
            ("Sources", DocType.folder, None)
        ], "a new library opens with its Sources folder and nothing else"
    finally:
        manager.close_all()


def test_reopening_a_library_never_grows_anything(tmp_path):
    """The regression the Inbox ruling fixed: open used to re-seed the Inbox forever.

    Reopening adds nothing beyond the one Sources folder, and a Sources folder the person
    deleted stays deleted across reopens.
    """
    from fichero_server.db.manager import DatabaseManager

    package = tmp_path / "Reopened.fichero"
    package.mkdir()
    manager = DatabaseManager()
    try:
        db = manager.get_database(package)
        keeper = Document(name="Keep Me", path="/keep-me.txt")
        db.save(keeper)
        manager.close_database(package)

        for _ in range(2):
            reopened = manager.get_database(package)
            names = sorted(doc.name for doc in reopened.query(Document))
            assert names == ["Keep Me", "Sources"], f"open seeded something: {names}"
            manager.close_database(package)

        db = manager.get_database(package)
        [sources] = db.query(Document, name="Sources")
        db.delete(sources)
        manager.close_database(package)

        for _ in range(2):
            reopened = manager.get_database(package)
            names = [doc.name for doc in reopened.query(Document)]
            assert names == ["Keep Me"], f"open re-made a deleted Sources: {names}"
            manager.close_database(package)
    finally:
        manager.close_all()


def test_a_user_made_inbox_folder_is_ordinary_content(tmp_path):
    """Nothing special-cases the name in the engine — no guard, no reseed."""
    from fichero_server.db.manager import DatabaseManager

    package = tmp_path / "UserInbox.fichero"
    package.mkdir()
    manager = DatabaseManager()
    try:
        db = manager.get_database(package)
        inbox = Document(name="Inbox", parent_id=None, doc_type=DocType.folder)
        db.save(inbox)
        manager.close_database(package)

        # It survives a reopen as itself...
        reopened = manager.get_database(package)
        assert inbox.id in [doc.id for doc in reopened.query(Document)]
        # ...and deleting it is not refused, nor undone by the next open.
        reopened.delete(inbox)
        manager.close_database(package)

        names = [doc.name for doc in manager.get_database(package).query(Document)]
        assert "Inbox" not in names
    finally:
        manager.close_all()
