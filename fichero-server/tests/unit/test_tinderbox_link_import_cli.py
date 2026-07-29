from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from fichero_cli import __main__ as cli
from fichero_server.importers.tinderbox_link_import import TinderboxLinkImportSummary


runner = CliRunner()


def test_import_tinderbox_links_cli_invokes_importer(monkeypatch, tmp_path):
    captured = {}

    def fake_import_tinderbox_links(client, *, library_path: Path, tbx_path: Path, reset: bool = False):
        captured["client"] = client
        captured["library_path"] = library_path
        captured["tbx_path"] = tbx_path
        captured["reset"] = reset
        return TinderboxLinkImportSummary(
            library_path=library_path,
            tbx_path=tbx_path,
            root_document_id="tbx-root",
            imported_notes=2,
            updated_notes=1,
            deleted_notes=1,
            skipped_notes=0,
            errors=[],
        )

    monkeypatch.setattr(
        "fichero_server.importers.tinderbox_link_import.import_tinderbox_links_via_http",
        fake_import_tinderbox_links,
    )

    result = runner.invoke(
        cli.app,
        [
            "--base-url",
            "http://remote-engine.test",
            "import-tinderbox-links",
            "--library-path",
            str(tmp_path / "tbx.fichero"),
            "--tbx-path",
            str(tmp_path / "notes.tbx"),
            "--reset",
        ],
    )

    assert result.exit_code == 0
    assert captured["reset"] is True
    assert captured["client"].base_url == "http://remote-engine.test"
    assert "imported_notes: 2" in result.output
    assert "updated_notes: 1" in result.output
    assert "deleted_notes: 1" in result.output
