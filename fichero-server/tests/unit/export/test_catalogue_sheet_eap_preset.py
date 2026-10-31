"""catalogue.export.eap-preset-reproduces-the-sheet, dates-in-the-archives-format, cells-from-attributes-never-guessed.

A box of kind eap_box with three folders (described by a fake model, typed by a person, undescribed with two blank
pages), read cell for cell from attributes alone. Invented names and text only.
"""
import sys

import pytest

from fichero_server import catalogue_sheet as sheet
from fichero_server.export_service import export_catalogue_xlsx
from fichero_server.models import Artifact
from fichero_server.models.prototype_template import template_for_prototype
from fichero_server.recipes import catalogue_step as step
from tests.unit.export.helpers import folder, page, read_xlsx

DESCRIPTION = (
    "Title: Pleito por una finca.\nDates: 17 de marzo de 1892\nDates EDTF: 1892-03-17\n"
    "Access points: Villa Sur\nScope and content: Un pleito.\nDescription: Pleito sobre una finca."
)


def _described(db, parent):
    f = folder(db, "Pleito A", parent, seq=1)
    art = Artifact(document_id=f.id, artifact_type=step.ARTIFACT_TYPE, content=DESCRIPTION, provider="p", model="m-1")
    db.save(art)
    step.put_in_attributes(db, f.id, DESCRIPTION, art.id, run_id="r1", provider="p", model="m-1")
    step.put_in_content(db, f.id, DESCRIPTION, art.id)
    for n in (1, 2):
        page(db, f"IMG_00{n}.jpg", f.id, seq=n)
    return f


@pytest.fixture
def box(db):
    box = folder(db, "Caja 12", proto="eap_box", attrs={"catalogue_original_reference": "Archivo Z, fondo 3"})
    _described(db, box.id)
    folder(db, "Carta B", box.id, seq=2, attrs={
        "catalogue_title": "Carta del alcalde", "catalogue_date_normalised": "1900-05",
        "catalogue_places": ["Villa Sur", "Río Claro"], "catalogue_people": ["Mora, Ana", "Luna, Pedro"],
        "catalogue_subjects": ["Children", "Commerce"], "catalogue_problems": "falta el sello",
    }, meta={"attribute_sources": {"catalogue_title": {"by": "person"}}})
    c = folder(db, "Legajo C", box.id, seq=3)
    for n, attrs in ((17, {"material": "blank"}), (18, {"material": "blank"}), (19, {"material": "blank"}),
                     (25, {"material": "blank"}), (26, {})):
        page(db, f"IMG_{n:03d}.jpg", c.id, attrs=attrs, seq=n)
    return box


def test_the_thirteen_columns_render_cell_for_cell(db, box, tmp_path):
    out = tmp_path / "c.xlsx"
    export_catalogue_xlsx(db, out, box.id)
    sheets, frozen = read_xlsx(out)
    name = "Caja 12 Catalogación básica"
    rows = sheets[name]
    assert frozen[name] == 3
    keys = [c.key for c in template_for_prototype(db, "eap_digital_folder")]
    assert len(keys) == 13 and len(rows[0]) == 13
    assert rows[0][1] == "Digital Folder Name" and rows[1][1] == "Nombre de carpeta digital"
    assert rows[1][0] == "Tu nombre" and rows[0][12] == "Related Subjects" and rows[1][12] == ""
    assert rows[2][1] == "Nombre de la carpeta; no se escribe a mano."
    described, typed, undescribed = rows[3:]
    assert described == [
        "Fichero (m-1)", "Pleito A", "IMG_001", "IMG_002", "2", "Pleito por una finca.",
        "Archivo Z, fondo 3", "17/Marzo/1892", "", "", DESCRIPTION,  # the content IS the description
        "sin líneas: IMG_001\u2013IMG_002; sin clasificar: Villa Sur", ""]
    assert typed == [
        "", "Carta B", "", "", "0", "Carta del alcalde", "Archivo Z, fondo 3", "Mayo/1900",
        "Villa Sur|Río Claro", "Mora, Ana|Luna, Pedro", "", "falta el sello", "Children|Commerce"]
    assert undescribed[:6] == ["", "Legajo C", "IMG_017", "IMG_026", "5", ""]
    assert undescribed[6:] == ["Archivo Z, fondo 3", "", "", "", "",
                              "en blanco: IMG_017\u2013IMG_019, IMG_025; sin líneas: IMG_026; faltan IMG_020\u2013IMG_024", ""]


def test_image_ranges_collapse_runs_only():
    assert sheet.image_ranges(["IMG_017", "IMG_018", "IMG_019", "IMG_025"]) == "IMG_017\u2013IMG_019, IMG_025"
    assert sheet.image_ranges(["a", "b"]) == "a, b" and sheet.image_ranges([]) == ""


def test_writing_the_workbook_never_loads_a_model_client(db, box, tmp_path):
    before = {m for m in sys.modules if m.startswith(("anthropic", "openai"))}
    export_catalogue_xlsx(db, tmp_path / "c.xlsx", box.id)
    assert {m for m in sys.modules if m.startswith(("anthropic", "openai"))} == before


def test_the_tema_sheet_holds_the_vocabulary_with_both_labels(db, box, tmp_path):
    export_catalogue_xlsx(db, tmp_path / "c.xlsx", box.id)
    tema = read_xlsx(tmp_path / "c.xlsx")[0]["Tema"]
    assert tema[0] == ["Related Subjects", "Tema"] and len(tema) == 100
    assert ["Children", "niños"] in tema and ["Anthropology", ""] in tema
