"""catalogue-workbook as a kept-export format: one Catálogo.xlsx for the project, never one per page."""
import pytest

from fichero_server import kept_export
from tests.unit.export.helpers import folder, page, read_xlsx


def _export(fmt="catalogue-workbook", per="document"):
    return {"id": "e1", "folder": "/unused", "format": fmt, "per": per}


def test_the_workbook_is_one_unit_named_catalogo(db):
    box = folder(db, "Caja 1", proto="eap_box")
    f = folder(db, "Doc", box.id, attrs={"catalogue_title": "Un título"})
    page(db, "IMG_001.jpg", f.id)
    units = kept_export._units(db, _export())
    assert [u.filename for u in units] == ["Catálogo.xlsx"]


def test_rendering_it_writes_the_catalogue_sheet(db, tmp_path):
    box = folder(db, "Caja 1", proto="eap_box")
    folder(db, "Doc", box.id, attrs={"catalogue_title": "Un título"})
    unit = kept_export._units(db, _export())[0]
    data = kept_export._render(db, _export(), unit)
    out = tmp_path / "c.xlsx"
    out.write_bytes(data)
    sheets, frozen = read_xlsx(out)
    assert frozen["Caja 1 Catalogación básica"] == 3
    assert sheets["Caja 1 Catalogación básica"][3][5] == "Un título"


def test_per_page_is_refused_in_a_sentence(db):
    with pytest.raises(kept_export.KeptExportRefused, match="one file for the project"):
        kept_export.keep(db, "/tmp", "catalogue-workbook", "page")
