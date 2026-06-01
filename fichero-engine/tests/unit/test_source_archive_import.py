from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from fichero import __main__ as cli
from fichero.source_archive_import import (
    import_chota_colombian_pacific_maps,
    import_archivo_judicial_medellin,
    import_ghc_catalogued_materials,
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


def test_import_archivo_judicial_medellin_ingests_catalogue(tmp_path):
    library = tmp_path / "ArchivoJudicial.fichero"
    catalogue = tmp_path / "Archivo Judicial de Medellin" / "Catalogue"
    (catalogue / "Batch-1").mkdir(parents=True)
    (catalogue / "Batch-1" / "entry-001.jpg").write_text("x", encoding="utf-8")
    (catalogue / "Batch-1" / "entry-002.pdf").write_text("x", encoding="utf-8")

    summary = import_archivo_judicial_medellin(
        library_path=library,
        catalogue_root=catalogue,
    )

    assert summary.provider == "archivo_judicial_medellin"
    assert summary.files_imported == 2
    assert summary.skipped == 0


def test_cli_import_archivo_judicial_invokes_importer(monkeypatch, tmp_path):
    called: dict = {}

    def fake_import(**kwargs):
        called.update(kwargs)
        from fichero.source_archive_import import SourceArchiveImportSummary

        return SourceArchiveImportSummary(
            provider="archivo_judicial_medellin",
            library_path=Path(kwargs["library_path"]),
            root_documents=1,
            files_imported=2,
            skipped=0,
            warnings=[],
        )

    monkeypatch.setattr(
        "fichero.source_archive_import.import_archivo_judicial_medellin",
        fake_import,
    )
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "import-archivo-judicial-medellin",
            "--library-path",
            str(tmp_path / "AJM.fichero"),
            "--catalogue-root",
            str(tmp_path / "Catalogue"),
        ],
    )
    assert result.exit_code == 0
    assert Path(called["library_path"]) == tmp_path / "AJM.fichero"


def test_import_ghc_catalogued_materials_ingests_roots(tmp_path):
    library = tmp_path / "GHC.fichero"
    acenet_root = tmp_path / "ACENET imports"
    catalogued_root = tmp_path / "GHC catalogued"
    acenet_root.mkdir(parents=True)
    catalogued_root.mkdir(parents=True)
    (acenet_root / "acen-001.jpg").write_text("x", encoding="utf-8")
    (catalogued_root / "ghc-001.pdf").write_text("x", encoding="utf-8")

    summary = import_ghc_catalogued_materials(
        library_path=library,
        acenet_root=acenet_root,
        catalogued_root=catalogued_root,
    )

    assert summary.provider == "ghc_catalogued_materials"
    assert summary.files_imported == 2
    assert summary.skipped == 0


def test_cli_import_ghc_catalogued_materials_invokes_importer(monkeypatch, tmp_path):
    called: dict = {}

    def fake_import(**kwargs):
        called.update(kwargs)
        from fichero.source_archive_import import SourceArchiveImportSummary

        return SourceArchiveImportSummary(
            provider="ghc_catalogued_materials",
            library_path=Path(kwargs["library_path"]),
            root_documents=2,
            files_imported=2,
            skipped=0,
            warnings=[],
        )

    monkeypatch.setattr(
        "fichero.source_archive_import.import_ghc_catalogued_materials",
        fake_import,
    )
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "import-ghc-catalogued-materials",
            "--library-path",
            str(tmp_path / "GHC.fichero"),
            "--acenet-root",
            str(tmp_path / "ACENET"),
            "--catalogued-root",
            str(tmp_path / "Catalogued"),
        ],
    )
    assert result.exit_code == 0
    assert Path(called["library_path"]) == tmp_path / "GHC.fichero"


def test_import_chota_colombian_pacific_maps_ingests_source_tree(tmp_path):
    library = tmp_path / "ChotaPacificMaps.fichero"
    source_root = tmp_path / "maps_southern_colombia"
    (source_root / "chota_valley").mkdir(parents=True)
    (source_root / "colombian_pacific").mkdir(parents=True)
    (source_root / "chota_valley" / "map-001.tif").write_text("x", encoding="utf-8")
    (source_root / "colombian_pacific" / "map-002.jpg").write_text("x", encoding="utf-8")

    summary = import_chota_colombian_pacific_maps(
        library_path=library,
        source_root=source_root,
    )

    assert summary.provider == "chota_colombian_pacific_maps"
    assert summary.files_imported == 2
    assert summary.skipped == 0


def test_cli_import_chota_colombian_pacific_maps_invokes_importer(monkeypatch, tmp_path):
    called: dict = {}

    def fake_import(**kwargs):
        called.update(kwargs)
        from fichero.source_archive_import import SourceArchiveImportSummary

        return SourceArchiveImportSummary(
            provider="chota_colombian_pacific_maps",
            library_path=Path(kwargs["library_path"]),
            root_documents=2,
            files_imported=2,
            skipped=0,
            warnings=[],
        )

    monkeypatch.setattr(
        "fichero.source_archive_import.import_chota_colombian_pacific_maps",
        fake_import,
    )
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "import-chota-colombian-pacific-maps",
            "--library-path",
            str(tmp_path / "Maps.fichero"),
            "--source-root",
            str(tmp_path / "maps_southern_colombia"),
        ],
    )
    assert result.exit_code == 0
    assert Path(called["library_path"]) == tmp_path / "Maps.fichero"
