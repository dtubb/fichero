"""The ingest allow-list and the serving allow-list must agree (#4230).

The engine had TWO independent notions of "a path we may touch":

* ``_is_allowed_local_path`` (ingest) — ``~/Desktop``, ``~/Documents``, …
* ``allowed_source_roots`` (serving) — the library package and storage only

``IngestMode.LINK`` is the DEFAULT, and a LINK import records the ORIGINAL
path. So a file the engine happily imported from ``~/Desktop`` resolved to
``None`` at serve time: "No source found", 404 on every thumbnail, for a file
sitting exactly where the user left it.

The authorisation model chosen here is **"this document was imported"**, not
"this path lives in a blessed directory":

* ``is_allowed_ingest_path`` is the ONE authority for what may enter a library.
* ``resolve_document_source_path`` serves a path RECORDED ON A DOCUMENT ROW if
  it is under the library/storage roots *or* under that same ingest authority.
  It is only ever reached with a path the engine itself wrote at ingest — the
  HTTP surface takes a document id, never a path.
* ``validate_stored_document_path`` (a CLIENT-supplied path on the update
  route) is deliberately NOT widened — writing a path is a different grant
  from reading one the engine recorded.

The agreement test below is the guardrail the issue asked for: divergence
fails the gate instead of surfacing as "No source found".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero.security.path_security import (
    allowed_source_roots,
    ingest_allowed_roots,
    is_allowed_ingest_path,
    resolve_document_source_path,
    resolve_under_allowed_roots,
    validate_stored_document_path,
)


@pytest.fixture()
def library(tmp_path: Path) -> Path:
    root = tmp_path / "Library.fichero"
    (root / "files").mkdir(parents=True)
    return root


class TestTheTwoListsAgree:
    """Every root importable in LINK mode must be servable."""

    def test_every_ingest_root_is_servable_for_a_recorded_path(self, library):
        """The guardrail: a root in one list must be honoured by the other.

        Widening the ingest list without widening the document-source resolver
        re-creates #4230 exactly; this fails when they diverge.
        """
        diverged = [
            root
            for root in ingest_allowed_roots()
            if resolve_document_source_path(root / "IMG_075.jpg", library) is None
        ]

        assert not diverged, f"importable but not servable: {diverged}"

    def test_a_desktop_link_import_is_servable(self, tmp_path, monkeypatch):
        """The reported case: ~/Desktop/NCM_Diary_1925/IMG_075.jpg."""
        home = tmp_path / "home"
        source = home / "Desktop" / "NCM_Diary_1925" / "IMG_075.jpg"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"jpeg")
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        library = tmp_path / "Library.fichero"
        library.mkdir()

        assert is_allowed_ingest_path(str(source)), "precondition: importable"
        assert resolve_document_source_path(source, library) == source.resolve()

    def test_the_narrow_serving_list_alone_still_rejects_it(self, tmp_path, monkeypatch):
        """Pins WHY the fix was needed — not a tautology against the old code."""
        home = tmp_path / "home"
        source = home / "Desktop" / "IMG_075.jpg"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"jpeg")
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        library = tmp_path / "Library.fichero"
        library.mkdir()

        assert resolve_under_allowed_roots(source, allowed_source_roots(library)) is None


class TestWhatStaysDenied:
    """Widening the serving side must not have opened the filesystem."""

    def test_a_path_outside_every_root_is_not_servable(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        # NOT anywhere under tmp_path: /private/var/folders IS an allowed
        # ingest root (it is where pytest tmp dirs live), so a "somewhere
        # else" path built from tmp_path passes and proves nothing.
        outsider = Path("/etc/passwd")
        library = tmp_path / "Library.fichero"
        library.mkdir()

        assert not is_allowed_ingest_path(str(outsider))
        assert resolve_document_source_path(outsider, library) is None

    def test_a_traversal_out_of_the_package_is_not_servable(self, tmp_path):
        """`path="../outside.txt"` must stay a 404.

        Found by `test_routes_storage.py::TestSourceRouteConfinement` while
        this widening was being written: pytest tmp dirs live under
        /private/var/folders, which IS an ingest root, so a `..` escape from
        the package landed in an allowed root and started serving. The wider
        half now applies only to absolute, `..`-free recorded paths.
        """
        library = tmp_path / "Library.fichero"
        (library / "files").mkdir(parents=True)
        outside = tmp_path / "outside.txt"
        outside.write_text("secret")

        assert resolve_document_source_path(library / ".." / "outside.txt", library) is None

    def test_a_symlink_out_of_the_package_is_not_servable(self, tmp_path):
        """A relative in-package path whose target is a symlink escape."""
        library = tmp_path / "Library.fichero"
        (library / "files").mkdir(parents=True)
        outside = tmp_path / "outside.txt"
        outside.write_text("secret")
        (library / "files" / "escape.txt").symlink_to(outside)

        from fichero.db.storage import resolve_source
        from fichero.models import Document

        doc = Document(name="escape.txt", path="files/escape.txt")

        assert resolve_source(doc, library_root=library) is None

    def test_a_client_supplied_stored_path_is_still_package_confined(
        self, tmp_path, monkeypatch
    ):
        """The update route's write grant is NOT widened by this change.

        A client may not point a document row at ~/Desktop; only ingest may,
        and only for a file it actually imported.
        """
        home = tmp_path / "home"
        desktop_file = home / "Desktop" / "IMG_075.jpg"
        desktop_file.parent.mkdir(parents=True)
        desktop_file.write_bytes(b"jpeg")
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        library = tmp_path / "Library.fichero"
        library.mkdir()

        with pytest.raises(ValueError):
            validate_stored_document_path(str(desktop_file), library)


class TestIngestRejectsLoudly:
    """A non-allow-listed path must fail at INGEST, not silently at serve time."""

    def test_the_ingest_route_refuses_a_disallowed_path(self, tmp_path, monkeypatch):
        from fastapi import HTTPException

        from fichero.api.routes.ingest.core import _validate_ingest_path

        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        outsider = Path("/etc/passwd")  # see the note in TestWhatStaysDenied

        with pytest.raises(HTTPException) as excinfo:
            _validate_ingest_path(str(outsider))

        assert excinfo.value.status_code == 403
        # Actionable, not just "denied": the message must name the path.
        assert str(outsider) in str(excinfo.value.detail)

    def test_the_ingest_route_accepts_a_path_it_can_serve(self, tmp_path, monkeypatch):
        from fichero.api.routes.ingest.core import _validate_ingest_path

        home = tmp_path / "home"
        source = home / "Desktop" / "IMG_075.jpg"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"jpeg")
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        library = tmp_path / "Library.fichero"
        library.mkdir()

        _validate_ingest_path(str(source))  # must not raise

        assert resolve_document_source_path(source, library) is not None


class TestResolveSourceServesALinkedFile:
    """End of the chain: db.storage.resolve_source, the function that 404'd."""

    def test_resolve_source_returns_a_linked_desktop_file(self, tmp_path, monkeypatch):
        from fichero.db.storage import resolve_source
        from fichero.models import Document

        home = tmp_path / "home"
        source = home / "Desktop" / "NCM_Diary_1925" / "IMG_075.jpg"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"jpeg")
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        library = tmp_path / "Library.fichero"
        library.mkdir()
        doc = Document(name="IMG_075.jpg", title="IMG_075", path=str(source))

        assert resolve_source(doc, library_root=library) == source.resolve()
