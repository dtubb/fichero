"""An exported page's filename carries its format's own extension, taken from the format registry
(archive's finding, 2026-09-28).

WHY: `page_export` kept its own table of extensions beside the registry and defaulted every format
it did not list to `.xml` -- so an hOCR export arrived as `x.xml` (hOCR is HTML: `.hocr`) and a
YOLO label file as `x.xml` (it is lines of numbers: `.txt`). A file named for the wrong format is
opened by the wrong program, or refused on import by a tool that trusts extensions; the app had
started renaming them itself, a second source of the same fact. If this regresses, a new format
exports as `.xml` whatever it is.

Every writable text format is exported through the app's route from a real imported page (the
Arabic PAGE file of `test_reader_directions`); the georeferencing formats need a georef pass and are
pinned by `test_a_georeference_exports_from_the_library.py`.
"""

from __future__ import annotations

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.formats import known_formats
from tests.unit.api.test_reader_directions import ARABIC, _import

GEOREF = {"iiif-georef", "qgis-points"}


def _text_formats():
    return sorted(spec.name for spec in known_formats() if spec.writes and spec.name not in GEOREF)


@pytest.mark.parametrize("name", _text_formats())
def test_each_format_exports_under_its_own_extension(db, client, name):
    spec = next(s for s in known_formats() if s.name == name)
    doc_id = _import(db, ARABIC)
    response = client.get(f"/api/documents/{doc_id}/export/{name}")
    assert response.status_code == 200, response.text
    filename = response.json()["filename"]
    assert filename.endswith(spec.file_extension), (name, filename)


def test_hocr_is_hocr_and_yolo_is_txt():
    """The two archive found, by name: neither is XML."""
    by_name = {spec.name: spec for spec in known_formats()}
    assert by_name["hocr"].file_extension == ".hocr"
    assert by_name["yolo"].file_extension == ".txt"
    assert {by_name[n].file_extension for n in ("pagexml", "alto", "tei")} == {".page.xml", ".alto.xml", ".tei.xml"}


def _export_name(client, doc_id: str, name: str) -> str:
    response = client.get(f"/api/documents/{doc_id}/export/{name}")
    assert response.status_code == 200, response.text
    return response.json()["filename"]


def test_an_imported_page_exported_in_its_own_format_carries_the_extension_once(db, client):
    """An imported page is named after its file (`x.page.xml`): taking only the last suffix off
    gave `x.page` and a PAGE export of it read `x.page.page.xml` (2026-09-28)."""
    from tests.unit.api.test_page_text_follows_the_file import SYRIAC, _import as import_file

    doc_id = import_file(db, SYRIAC)
    assert _export_name(client, doc_id, "pagexml") == "escriptorium_syriac_onb-syr1-0001.page.xml"


def test_an_alto_import_exported_as_tei_is_named_tei_not_alto(db, client):
    from tests.unit.api.test_page_text_follows_the_file import CLM, _import as import_file

    doc_id = import_file(db, CLM)
    assert _export_name(client, doc_id, "tei") == "escriptorium_latin-mufi_clm13027-38r.tei.xml"


def test_an_image_name_keeps_its_stem_and_every_dot_in_it():
    from fichero_server.page_export import export_stem

    assert export_stem("onb-syr1.0001.jpg", "doc") == "onb-syr1.0001"
    assert export_stem("folio 3r.tif", "doc") == "folio 3r"
    assert export_stem("scan.v2.page.xml", "doc") == "scan.v2"            # the sidecar suffix goes, the dots stay
    assert export_stem("onb-syr1-0001.page.jpg", "doc") == "onb-syr1-0001"  # an image named after its sidecar
    assert export_stem(None, "doc-123") == "doc-123"
