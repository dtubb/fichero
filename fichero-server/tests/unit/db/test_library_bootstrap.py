"""A library is bootstrapped with NOTHING in it.

Ruling 2026-08-31: there is no default Inbox. The library root IS the drop
zone — loose files land there and are visible in both surfaces that list roots
— so the folder was interface crud. ``db/library_bootstrap.py`` (which held
``INBOX_NAME`` and ``ensure_inbox_folder``) is deleted along with every path
that called it: nothing in the app or the engine creates an Inbox any more.

A root folder named "Inbox" is now ordinary user content. It has no guard
(delete/move/rename all work, like any folder the user made); the only thing
that still knows the name is the Swift root-drop routing, which files loose
drops into one the USER made, and the sidebar, which hoists it.
"""

from fichero_server.models import DocType, Document


def test_a_new_library_is_bootstrapped_empty(tmp_path, monkeypatch):
    """No Inbox, no anything — `get_database` seeds no documents at all."""
    from fichero_server.db.manager import DatabaseManager

    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    monkeypatch.setenv("FICHERO_SKIP_DERIVATIVE_RESUME", "1")

    package = tmp_path / "Fresh.fichero"
    package.mkdir()
    manager = DatabaseManager()
    db = manager.get_database(package)
    try:
        assert list(db.query(Document)) == [], "a new library must open EMPTY"
    finally:
        manager.close_all()


def test_reopening_a_library_never_grows_an_inbox(tmp_path, monkeypatch):
    """The regression this replaces: open used to re-seed the Inbox forever.

    A user who deleted it got it back on every reopen. Open is now inert — it
    adds nothing, and a library the user left empty stays empty.
    """
    from fichero_server.db.manager import DatabaseManager

    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    monkeypatch.setenv("FICHERO_SKIP_DERIVATIVE_RESUME", "1")

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
            names = [doc.name for doc in reopened.query(Document)]
            assert names == ["Keep Me"], f"open seeded something: {names}"
            manager.close_database(package)
    finally:
        manager.close_all()


def test_a_user_made_inbox_folder_is_ordinary_content(tmp_path, monkeypatch):
    """Nothing special-cases the name in the engine — no guard, no reseed."""
    from fichero_server.db.manager import DatabaseManager

    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    monkeypatch.setenv("FICHERO_SKIP_DERIVATIVE_RESUME", "1")

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
        assert [doc.id for doc in reopened.query(Document)] == [inbox.id]
        # ...and deleting it is not refused, nor undone by the next open.
        reopened.delete(inbox)
        manager.close_database(package)

        assert list(manager.get_database(package).query(Document)) == []
    finally:
        manager.close_all()
