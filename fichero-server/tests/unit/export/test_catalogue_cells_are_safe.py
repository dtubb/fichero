"""The catalogue workbook opens in Excel whatever the page text holds: no control character XML refuses, no cell over Excel's
limit, no CSV cell that runs as a formula."""
import zipfile

from fichero_server.export_service import _csv_bytes, export_catalogue_xlsx
from tests.unit.export.helpers import folder, page, read_xlsx


def _world(db, text):
    box = folder(db, "Caja", proto="eap_box")
    doc = folder(db, "Pleito", box.id, seq=1)
    p = page(db, "IMG_001.jpg", doc.id, seq=1)
    p.page_content = text
    db.save(p)
    return box


def test_a_form_feed_and_a_vertical_tab_in_page_text_leave_a_readable_workbook(db, tmp_path):
    box = _world(db, "primera\x0clínea\x0bsegunda\x00fin\ttab\nnueva")
    export_catalogue_xlsx(db, tmp_path / "c.xlsx", box.id)
    sheets, _ = read_xlsx(tmp_path / "c.xlsx")  # the XML parses
    text = " ".join(cell for row in sheets["Páginas"] for cell in row)
    assert "primeralíneasegundafin" in text


def test_a_page_over_the_cell_limit_is_cut_with_a_note(db, tmp_path):
    box = _world(db, "a" * 40000)
    export_catalogue_xlsx(db, tmp_path / "c.xlsx", box.id)
    sheets, _ = read_xlsx(tmp_path / "c.xlsx")
    cells = [cell for row in sheets["Páginas"] for cell in row]
    assert max(len(c) for c in cells) <= 32767
    assert any("cortado" in c for c in cells)


def test_a_csv_cell_that_would_run_as_a_formula_is_neutralised():
    raw = _csv_bytes([["=1+1", "+x", "-y", "@z", "plain", "a=b"]]).decode("utf-8-sig")
    assert raw.strip() == '"\'=1+1","\'+x","\'-y","\'@z","plain","a=b"'


def test_the_csv_zip_carries_the_neutralised_cells(db, tmp_path):
    box = _world(db, "=HYPERLINK(\"x\")")
    result = export_catalogue_xlsx(db, tmp_path / "c", box.id, file_format="csv")
    with zipfile.ZipFile(result.output_path) as z:
        assert '"\'=HYPERLINK' in z.read("Páginas.csv").decode("utf-8-sig")
