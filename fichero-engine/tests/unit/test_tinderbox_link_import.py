from __future__ import annotations

from pathlib import Path

import pytest

from fichero.importers.tinderbox_link_import import import_tinderbox_links_via_http
from fichero.tinderbox_link_import import parse_tinderbox_notes


def _write_tbx(path: Path, body: str) -> None:
    path.write_text(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<tbx>\n" + body + "\n</tbx>\n",
        encoding="utf-8",
    )


class FakeDoc:
    def __init__(self, doc_id: str, path: str, *, doc_type: str, metadata: dict | None = None) -> None:
        self.id = doc_id
        self.path = path
        self.doc_type = doc_type
        self.metadata = metadata or {}


class FakeClient:
    def __init__(self) -> None:
        self.created_library: str | None = None
        self.docs: dict[str, list[FakeDoc]] = {}
        self.next_id = 0

    def create_library(self, path: str) -> None:
        self.created_library = path

    def list_documents(self, *, parent_id: str | None = None, **_kwargs):
        return list(self.docs.get(parent_id or "", []))

    def request(self, method: str, path: str, *, json=None, **_kwargs):
        if method == "POST" and path == "/api/documents":
            self.next_id += 1
            doc = FakeDoc(
                f"doc-{self.next_id}",
                json["path"],
                doc_type=json["doc_type"],
                metadata=json.get("metadata"),
            )
            self.docs.setdefault(json.get("parent_id") or "", []).append(doc)
            return {"id": doc.id, **json}
        if method == "PUT" and path.startswith("/api/documents/"):
            doc_id = path.rsplit("/", 1)[-1]
            for docs in self.docs.values():
                for doc in docs:
                    if doc.id == doc_id:
                        doc.path = json["path"]
                        doc.metadata = json.get("metadata") or {}
                        return {"id": doc.id, **json}
            raise AssertionError(f"missing doc for update: {doc_id}")
        if method == "DELETE" and path.startswith("/api/documents/"):
            doc_id = path.rsplit("/", 1)[-1]
            for key, docs in self.docs.items():
                self.docs[key] = [doc for doc in docs if doc.id != doc_id]
            return None
        raise AssertionError(f"unexpected request: {method} {path}")


def test_import_tinderbox_links_via_http_upserts_and_removes_deleted_notes(tmp_path):
    library_path = tmp_path / "tbx-http.fichero"
    tbx_path = tmp_path / "notes-http.tbx"

    _write_tbx(
        tbx_path,
        """
<note ID="n1" Name="First" Path="/One" Text="alpha text" Tags="a,b" Modified="2024-01-01" />
<note ID="n2" Name="Second" Path="/Two" Text="beta text" />
        """.strip(),
    )

    client = FakeClient()
    summary = import_tinderbox_links_via_http(
        client,
        library_path=library_path,
        tbx_path=tbx_path,
    )

    root_docs = client.docs.get("", [])
    assert len(root_docs) == 1
    root_id = root_docs[0].id
    assert summary.imported_notes == 2
    assert len(client.docs[root_id]) == 2

    _write_tbx(
        tbx_path,
        """
<note ID="n1" Name="First updated" Path="/One" Text="alpha updated" Tags="a,c" Modified="2024-01-02" />
        """.strip(),
    )

    summary2 = import_tinderbox_links_via_http(
        client,
        library_path=library_path,
        tbx_path=tbx_path,
    )

    assert summary2.updated_notes == 1
    assert summary2.deleted_notes == 1
    assert len(client.docs[root_id]) == 1
    assert client.created_library == str(library_path.resolve())


def test_parse_tinderbox_notes_rejects_billion_laughs_entities(tmp_path):
    tbx_path = tmp_path / "evil.tbx"
    tbx_path.write_text(
        """<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
]>
<tinderbox><note id="n1" name="&lol1;"/></tinderbox>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="entity declarations"):
        parse_tinderbox_notes(tbx_path)
