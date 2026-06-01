from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from fichero import __main__ as cli
from fichero.source_archive_import import (
    import_istmina_mineria,
    import_newton_marshall_diary,
)


def test_import_newton_marshall_diary_ingests_tree(tmp_path):
    library = tmp_path / "NewtonMarshall.fichero"
    source = tmp_path / "Newton C Marshall Diary"
    (source / "BoxA").mkdir(parents=True)
    (source / "BoxA" / "page001.jpg").write_text("x", encoding="utf-8")
    (source / "BoxA" / "page002.jpg").write_text("x", encoding="utf-8")

    summary = import_newton_marshall_diary(
        library_path=library,
        source_path=source,
    )

    assert summary.provider == "newton_marshall_diary"
    assert summary.files_imported == 2
    assert summary.skipped == 0


def test_import_istmina_mineria_ingests_multiple_roots(tmp_path):
    library = tmp_path / "Istmina.fichero"
    t_root = tmp_path / "Istmina_Mineria_Transcripcion"
    s_root = tmp_path / "05 Added to spreadsheet"
    r_root = tmp_path / "04 Transcribed and catalogued, awaiting human check"
    for root in (t_root, s_root, r_root):
        root.mkdir(parents=True)
    (t_root / "doc-1.jpg").write_text("x", encoding="utf-8")
    (s_root / "sheet-row-1.txt").write_text("x", encoding="utf-8")
    (r_root / "review-1.txt").write_text("x", encoding="utf-8")

    summary = import_istmina_mineria(
        library_path=library,
        transcript_root=t_root,
        spreadsheet_root=s_root,
        review_root=r_root,
    )

    assert summary.provider == "istmina_mineria"
    assert summary.files_imported == 3
    assert summary.skipped == 0


def test_cli_import_newton_marshall_invokes_importer(monkeypatch, tmp_path):
    called: dict = {}

    def fake_import(**kwargs):
        called.update(kwargs)
        from fichero.source_archive_import import SourceArchiveImportSummary

        return SourceArchiveImportSummary(
            provider="newton_marshall_diary",
            library_path=Path(kwargs["library_path"]),
            root_documents=1,
            files_imported=2,
            skipped=0,
            warnings=[],
        )

    monkeypatch.setattr(
        "fichero.source_archive_import.import_newton_marshall_diary",
        fake_import,
    )
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "import-newton-marshall-diary",
            "--library-path",
            str(tmp_path / "N.fichero"),
            "--source-path",
            str(tmp_path / "Newton"),
        ],
    )
    assert result.exit_code == 0
    assert Path(called["library_path"]) == tmp_path / "N.fichero"
