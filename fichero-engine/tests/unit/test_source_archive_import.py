from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from fichero import __main__ as cli
from fichero.importers.source_archive_import import (
    import_chota_colombian_pacific_maps,
    import_archivo_judicial_medellin,
    import_archivo_judicial_medellin_via_http,
    import_ghc_catalogued_materials,
    import_ghc_catalogued_materials_via_http,
    import_istmina_mineria,
    import_istmina_mineria_via_http,
    import_newton_marshall_diary,
    import_newton_marshall_diary_via_http,
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


def test_import_istmina_mineria_via_http_ingests_multiple_roots(tmp_path):
    library = tmp_path / "Istmina.fichero"
    t_root = tmp_path / "Istmina_Mineria_Transcripcion"
    s_root = tmp_path / "05 Added to spreadsheet"
    r_root = tmp_path / "04 Transcribed and catalogued, awaiting human check"
    for root in (t_root, s_root, r_root):
        root.mkdir(parents=True)
    (t_root / "doc-1.jpg").write_text("x", encoding="utf-8")
    (s_root / "sheet-row-1.txt").write_text("x", encoding="utf-8")
    (r_root / "review-1.txt").write_text("x", encoding="utf-8")
    (r_root / "ignore.bin").write_text("x", encoding="utf-8")

    client = FakeClient()
    summary = import_istmina_mineria_via_http(
        client,
        library_path=library,
        transcript_root=t_root,
        spreadsheet_root=s_root,
        review_root=r_root,
    )

    assert summary.provider == "istmina_mineria"
    assert summary.files_imported == 3
    assert summary.skipped == 1
    assert client.created_library == str(library.resolve())


def test_cli_import_newton_marshall_invokes_importer(monkeypatch, tmp_path):
    called: dict = {}

    def fake_import(client, **kwargs):
        called.update({"client": client, **kwargs})
        from fichero.importers.source_archive_import import SourceArchiveImportSummary

        return SourceArchiveImportSummary(
            provider="newton_marshall_diary",
            library_path=Path(kwargs["library_path"]),
            root_documents=1,
            files_imported=2,
            skipped=0,
            warnings=[],
        )

    monkeypatch.setattr(
        "fichero.importers.source_archive_import.import_newton_marshall_diary_via_http",
        fake_import,
    )
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "--base-url",
            "http://remote-engine.test",
            "import-newton-marshall-diary",
            "--library-path",
            str(tmp_path / "N.fichero"),
            "--source-path",
            str(tmp_path / "Newton"),
        ],
    )
    assert result.exit_code == 0
    assert Path(called["library_path"]) == tmp_path / "N.fichero"
    assert called["client"].base_url == "http://remote-engine.test"


class FakeDoc:
    def __init__(self, doc_id: str, path: str):
        self.id = doc_id
        self.path = path


class FakeClient:
    def __init__(self) -> None:
        self.created_library: str | None = None
        self.docs: dict[str, list[FakeDoc]] = {}
        self.imported_files: list[tuple[Path, str | None]] = []
        self.next_id = 0

    def create_library(self, path: str) -> None:
        self.created_library = path

    def list_documents(self, *, parent_id: str | None = None, **_kwargs) -> list[FakeDoc]:
        return list(self.docs.get(parent_id or "", []))

    def request(self, method: str, path: str, *, json=None, **_kwargs):
        if method == "POST" and path == "/api/documents":
            self.next_id += 1
            doc = FakeDoc(f"doc-{self.next_id}", json["path"])
            self.docs.setdefault(json.get("parent_id") or "", []).append(doc)
            return {"id": doc.id, **json}
        raise AssertionError(f"unexpected request: {method} {path}")

    def import_file(self, path: Path, parent_id: str | None = None):
        self.next_id += 1
        doc = FakeDoc(f"file-{self.next_id}", str(path))
        self.docs.setdefault(parent_id or "", []).append(doc)
        self.imported_files.append((path, parent_id))
        return doc


def test_import_newton_marshall_diary_via_http_imports_tree(tmp_path):
    library = tmp_path / "NewtonMarshall.fichero"
    source = tmp_path / "Newton C Marshall Diary"
    (source / "BoxA").mkdir(parents=True)
    (source / "BoxA" / "page001.jpg").write_text("x", encoding="utf-8")
    (source / "BoxA" / "page002.jpg").write_text("x", encoding="utf-8")
    (source / "BoxA" / "ignore.bin").write_text("x", encoding="utf-8")

    client = FakeClient()
    summary = import_newton_marshall_diary_via_http(
        client,
        library_path=library,
        source_path=source,
    )

    assert summary.provider == "newton_marshall_diary"
    assert summary.files_imported == 2
    assert summary.skipped == 1
    assert client.created_library == str(library.resolve())


def test_cli_import_istmina_mineria_invokes_http_importer(monkeypatch, tmp_path):
    called: dict = {}

    def fake_import(client, **kwargs):
        called.update({"client": client, **kwargs})
        from fichero.importers.source_archive_import import SourceArchiveImportSummary

        return SourceArchiveImportSummary(
            provider="istmina_mineria",
            library_path=Path(kwargs["library_path"]),
            root_documents=4,
            files_imported=3,
            skipped=0,
            warnings=[],
        )

    monkeypatch.setattr(
        "fichero.importers.source_archive_import.import_istmina_mineria_via_http",
        fake_import,
    )
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "--base-url",
            "http://remote-engine.test",
            "import-istmina-mineria",
            "--library-path",
            str(tmp_path / "I.fichero"),
            "--transcript-root",
            str(tmp_path / "Transcripts"),
            "--spreadsheet-root",
            str(tmp_path / "Spreadsheet"),
            "--review-root",
            str(tmp_path / "Review"),
        ],
    )
    assert result.exit_code == 0
    assert Path(called["library_path"]) == tmp_path / "I.fichero"
    assert called["client"].base_url == "http://remote-engine.test"


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

    def fake_import(client, **kwargs):
        called.update({"client": client, **kwargs})
        from fichero.importers.source_archive_import import SourceArchiveImportSummary

        return SourceArchiveImportSummary(
            provider="archivo_judicial_medellin",
            library_path=Path(kwargs["library_path"]),
            root_documents=1,
            files_imported=2,
            skipped=0,
            warnings=[],
        )

    monkeypatch.setattr(
        "fichero.importers.source_archive_import.import_archivo_judicial_medellin_via_http",
        fake_import,
    )
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "--base-url",
            "http://remote-engine.test",
            "import-archivo-judicial-medellin",
            "--library-path",
            str(tmp_path / "AJM.fichero"),
            "--catalogue-root",
            str(tmp_path / "Catalogue"),
        ],
    )
    assert result.exit_code == 0
    assert Path(called["library_path"]) == tmp_path / "AJM.fichero"
    assert called["client"].base_url == "http://remote-engine.test"


def test_import_archivo_judicial_medellin_via_http_ingests_catalogue(tmp_path):
    library = tmp_path / "ArchivoJudicial.fichero"
    catalogue = tmp_path / "Archivo Judicial de Medellin" / "Catalogue"
    (catalogue / "Batch-1").mkdir(parents=True)
    (catalogue / "Batch-1" / "entry-001.jpg").write_text("x", encoding="utf-8")
    (catalogue / "Batch-1" / "entry-002.pdf").write_text("x", encoding="utf-8")
    (catalogue / "Batch-1" / "ignore.bin").write_text("x", encoding="utf-8")

    client = FakeClient()
    summary = import_archivo_judicial_medellin_via_http(
        client,
        library_path=library,
        catalogue_root=catalogue,
    )

    assert summary.provider == "archivo_judicial_medellin"
    assert summary.files_imported == 2
    assert summary.skipped == 1
    assert client.created_library == str(library.resolve())


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


def test_import_ghc_catalogued_materials_via_http_ingests_roots(tmp_path):
    library = tmp_path / "GHC.fichero"
    acenet_root = tmp_path / "ACENET imports"
    catalogued_root = tmp_path / "GHC catalogued"
    acenet_root.mkdir(parents=True)
    catalogued_root.mkdir(parents=True)
    (acenet_root / "acen-001.jpg").write_text("x", encoding="utf-8")
    (catalogued_root / "ghc-001.pdf").write_text("x", encoding="utf-8")

    client = FakeClient()
    summary = import_ghc_catalogued_materials_via_http(
        client,
        library_path=library,
        acenet_root=acenet_root,
        catalogued_root=catalogued_root,
    )

    assert summary.provider == "ghc_catalogued_materials"
    assert summary.files_imported == 2
    assert summary.skipped == 0
    assert client.created_library == str(library.resolve())


def test_cli_import_ghc_catalogued_materials_invokes_importer(monkeypatch, tmp_path):
    called: dict = {}

    def fake_import(client, **kwargs):
        called.update({"client": client, **kwargs})
        from fichero.importers.source_archive_import import SourceArchiveImportSummary

        return SourceArchiveImportSummary(
            provider="ghc_catalogued_materials",
            library_path=Path(kwargs["library_path"]),
            root_documents=2,
            files_imported=2,
            skipped=0,
            warnings=[],
    )

    monkeypatch.setattr(
        "fichero.importers.source_archive_import.import_ghc_catalogued_materials_via_http",
        fake_import,
    )
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "--base-url",
            "http://remote-engine.test",
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
    assert called["client"].base_url == "http://remote-engine.test"


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
