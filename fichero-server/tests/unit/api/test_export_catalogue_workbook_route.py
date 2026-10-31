"""catalogue.export.on-demand-route (catalogue-export.md step 2.4): the file comes back, no local path goes in."""
import base64
import io
import zipfile

from fichero_server import kept_export
from tests.unit.export.helpers import folder, page, read_xlsx


def _box(db):
    box = folder(db, "Caja", proto="eap_box")
    f = folder(db, "Doc", box.id, attrs={"catalogue_title": "Un título"})
    page(db, "IMG_001.jpg", f.id, seq=1)
    return box


def _post(client, **body):
    r = client.post("/api/export/catalogue-workbook", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_workbook_comes_back_as_the_response(client, db, tmp_path):
    box = _box(db)
    got = _post(client, target_id=box.id)
    assert got["filename"] == "Catálogo.xlsx" and got["row_count"] == 1 and got["sheets"][0] == "Caja Catalogación básica"
    (tmp_path / "c.xlsx").write_bytes(base64.b64decode(got["content_base64"]))
    assert read_xlsx(tmp_path / "c.xlsx")[0]["Caja Catalogación básica"][3][5] == "Un título"


def test_csv_is_a_zip_of_one_file_per_sheet(client, db):
    box = _box(db)
    got = _post(client, target_id=box.id, format="csv")
    assert got["filename"] == "Catálogo.zip"
    names = zipfile.ZipFile(io.BytesIO(base64.b64decode(got["content_base64"]))).namelist()
    assert "Tema.csv" in names and "Notas.csv" in names


def test_a_named_prototype_and_omitted_proposals_reach_the_builder(client, db):
    box = _box(db)
    got = _post(client, target_id=box.id, prototype_key="eap_digital_folder_en", proposals="omitted")
    assert got["row_count"] == 1


def test_an_unknown_scope_is_a_404_and_no_path_is_accepted(client, db):
    assert client.post("/api/export/catalogue-workbook", json={"target_id": "nope"}).status_code == 404
    from fichero_server.api.routes.ingest.export import CatalogueWorkbookRequest

    assert "output_path" not in CatalogueWorkbookRequest.model_fields


def test_a_kept_export_id_queues_the_write_instead(client, db, tmp_path):
    box = _box(db)
    out = tmp_path / "kept"
    out.mkdir()
    export_id = kept_export.keep(db, str(out), "catalogue-workbook", "document")
    got = _post(client, target_id=box.id, kept_export_id=export_id)
    assert got["job_id"] and got["content_base64"] is None
    assert client.post("/api/export/catalogue-workbook", json={"kept_export_id": "x"}).status_code == 404


def test_a_workbook_that_only_reads_does_not_ask_for_the_write_door():
    from fichero_server.api.main import get_library_database_for_write
    from fichero_server.api.routes.ingest.export import router

    route = next(r for r in router.routes if r.path.endswith("/catalogue-workbook"))
    assert get_library_database_for_write not in {d.call for d in route.dependant.dependencies}
