from __future__ import annotations

import base64
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fichero import __main__ as cli
from fichero.slipbox_import import (
    decode_tinderbox_text,
    import_slipbox_via_http,
    iter_slipbox_files,
    iter_tinderbox_notes,
)


runner = CliRunner()


def _tbx(path: Path, *, text: str = "anthropology of writing") -> Path:
    payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8" ?>
<tinderbox version="2">
  <item ID="note-1" Creator="Daniel Tubb" proto="pSlip">
    <attribute name="Name">Writing note</attribute>
    <attribute name="Created">2026-05-27T10:00:00-03:00</attribute>
    <text>{payload}</text>
  </item>
</tinderbox>
""",
        encoding="utf-8",
    )
    return path


def test_iter_tinderbox_notes_decodes_base64_text(tmp_path):
    notes = list(iter_tinderbox_notes(_tbx(tmp_path / "sample.tbx")))

    assert len(notes) == 1
    assert notes[0].external_id == "note-1"
    assert notes[0].name == "Writing note"
    assert notes[0].text == "anthropology of writing"
    assert notes[0].attributes["Created"] == "2026-05-27T10:00:00-03:00"


def test_iter_tinderbox_notes_rejects_billion_laughs_entities(tmp_path):
    tbx = tmp_path / "evil.tbx"
    tbx.write_text(
        """<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
]>
<tinderbox><item id="n1" name="&lol1;"/></tinderbox>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="entity declarations"):
        list(iter_tinderbox_notes(tbx))


def test_decode_tinderbox_text_strips_rtf_payload():
    rtf = r"{\rtf1\ansi This is \b important\b0.\par Next line.}"
    encoded = base64.b64encode(rtf.encode("utf-8")).decode("ascii")

    decoded = decode_tinderbox_text(encoded)

    assert "important" in decoded
    assert "Next line" in decoded


def test_iter_slipbox_files_skips_hidden_and_virtualenv(tmp_path):
    root = tmp_path / "slipbox"
    (root / ".venv").mkdir(parents=True)
    (root / "notes").mkdir(parents=True)
    (root / ".venv" / "ignored.md").write_text("no", encoding="utf-8")
    (root / "notes" / "kept.md").write_text("yes", encoding="utf-8")
    (root / ".DS_Store").write_text("", encoding="utf-8")

    files = list(iter_slipbox_files(root))

    assert files == [root / "notes" / "kept.md"]


def test_cli_import_slipbox_invokes_importer(monkeypatch, tmp_path):
    calls = []

    def fake_import_slipbox(_client, **kwargs):
        from fichero.slipbox_import import SlipboxImportSummary

        calls.append(kwargs)
        return SlipboxImportSummary(
            library_path=kwargs["library_path"],
            root_document_id="root-1",
            tinderbox_notes=1,
            filesystem_files=2,
            skipped_files=3,
            errors=[],
        )

    monkeypatch.setattr(
        "fichero.importers.slipbox_import.import_slipbox_via_http",
        fake_import_slipbox,
    )

    result = runner.invoke(
        cli.app,
        [
            "--base-url",
            "http://remote-engine.test",
            "import-slipbox",
            "--library-path",
            str(tmp_path / "Sample.fichero"),
            "--filesystem-root",
            str(tmp_path / "slipbox"),
            "--tinderbox",
            str(tmp_path / "sample.tbx"),
            "--limit",
            "5",
            "--reset",
        ],
    )

    assert result.exit_code == 0
    assert calls[0]["limit"] == 5
    assert calls[0]["reset"] is True
    assert "tinderbox_notes: 1" in result.output
    assert "filesystem_files: 2" in result.output


def test_import_slipbox_via_http_uses_remote_routes(tmp_path):
    fs_root = tmp_path / "slipbox"
    fs_root.mkdir()
    fs_note = fs_root / "fieldwork.md"
    fs_note.write_text("fieldwork and authorship", encoding="utf-8")
    tbx = _tbx(tmp_path / "sample.tbx", text="Tinderbox sovereignty note")
    library = tmp_path / "Slipbox.fichero"

    class FakeClient:
        def __init__(self):
            self.next_id = 1
            self.created_libraries: list[str] = []
            self.documents_by_parent: dict[str | None, list[object]] = {}
            self.imported_files: list[tuple[Path, str | None]] = []

        def create_library(self, path: str):
            self.created_libraries.append(path)
            return {"path": path, "created": True}

        def list_documents(self, *, parent_id=None, **_kwargs):
            return list(self.documents_by_parent.get(parent_id, []))

        def request(self, method: str, path: str, *, json=None, **_kwargs):
            assert path.startswith("/api/documents")
            if method == "POST":
                doc_id = f"doc-{self.next_id}"
                self.next_id += 1
                payload = {"id": doc_id, **(json or {})}
                doc = type("Doc", (), payload)
                self.documents_by_parent.setdefault(json.get("parent_id"), []).append(doc)
                return payload
            if method == "PUT":
                doc_id = path.rsplit("/", 1)[-1]
                for docs in self.documents_by_parent.values():
                    for doc in docs:
                        if getattr(doc, "id", None) == doc_id:
                            for key, value in (json or {}).items():
                                setattr(doc, key, value)
                            return {"id": doc_id, **(json or {})}
            raise AssertionError(f"unexpected request {method} {path}")

        def import_file(self, path: str | Path, parent_id: str | None = None):
            self.imported_files.append((Path(path), parent_id))
            return {"id": f"import-{len(self.imported_files)}"}

    client = FakeClient()

    summary = import_slipbox_via_http(
        client,
        library_path=library,
        filesystem_root=fs_root,
        tinderbox_path=tbx,
        auto_embed=False,
    )

    assert client.created_libraries == [str(library)]
    assert summary.tinderbox_notes == 1
    assert summary.filesystem_files == 1
    assert summary.errors == []
    assert client.imported_files == [(fs_note, "doc-3")]
