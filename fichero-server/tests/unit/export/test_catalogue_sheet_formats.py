"""catalogue.export.xlsx-and-csv, authority sheets, kg sheets, notas and faltantes (catalogue-export.md step 2.1/2.2)."""
import zipfile

from fichero_server import catalogue_sheet as sheet
from fichero_server.export_service import export_catalogue_xlsx
from fichero_server.models.checking import CheckVerdict  # noqa: F401
from fichero_server.models.knowledge import (
    AttributionStep, EntityCurationState, EntityType, KnowledgeClaim, KnowledgeEntity,
)
from tests.unit.export.helpers import folder, page, read_xlsx

ORDER = ["Caja 12 Catalogación básica", "Faltantes", "Personas", "Lugares", "Entidades", "Tema", "Catálogo", "Páginas",
         "Nombres", "Declaraciones", "Notas"]


def _box(db):
    box = folder(db, "Caja 12", proto="eap_box")
    a = folder(db, "Pleito A", box.id, seq=1, attrs={
        "catalogue_title": "Pleito por una finca", "catalogue_dates": "mayo de 1900", "catalogue_date_normalised": "1900-05",
        "catalogue_people": ["Mora, Ana"], "catalogue_places": ["Villa Sur"], "catalogue_institutions": ["Juzgado"],
    }, meta={"attribute_sources": {"catalogue_title": {"by": "machine", "model": "m-1", "step": "catalogue", "run_id": "r1",
                                                       "said": "el título"}}})
    page(db, "IMG_001.jpg", a.id, seq=1, meta={})
    page(db, "IMG_003.jpg", a.id, seq=2)  # a gap: IMG_002 is missing
    folder(db, "Legajo B", box.id, seq=2, attrs={"catalogue_title": "Cartas"})
    ana = KnowledgeEntity(canonical_name="Mora, Ana", entity_type=EntityType.person, curation_state=EntityCurationState.verified,
                          metadata={"given_names": "Ana", "surnames": "Mora"}, source_document_ids=[a.id])
    sur = KnowledgeEntity(canonical_name="Villa Sur", entity_type=EntityType.location, source_document_ids=[a.id],
                          metadata={"place_type": "pueblo"},
                          attribution_chain=[AttributionStep(role="extractor", name="spacy", label="es_core_news_sm")])
    for e in (ana, sur):
        db.save(e)
    db.save(KnowledgeClaim(text="Ana demandó", source_document_id=a.id, subject_canonical="Ana", predicate_verb="demandó",
                           object_phrase="a Pedro", source_excerpt="Ana demandó a Pedro"))
    return box


def test_the_sheets_come_in_the_specs_order_and_an_empty_one_keeps_its_header(db, tmp_path):
    box = _box(db)
    export_catalogue_xlsx(db, tmp_path / "c.xlsx", box.id)
    sheets, frozen = read_xlsx(tmp_path / "c.xlsx")
    assert list(sheets) == ORDER
    assert frozen["Personas"] == 2 and frozen["Faltantes"] == 3
    scratch = folder(db, "Vacía")
    export_catalogue_xlsx(db, tmp_path / "e.xlsx", scratch.id)
    empty = read_xlsx(tmp_path / "e.xlsx")[0]
    assert list(empty)[1:] == ORDER[1:] and empty["Personas"][0][0] == "Forma en el catálogo" and len(empty["Personas"]) == 2


def test_faltantes_holds_only_the_rows_with_a_gap(db, tmp_path):
    box = _box(db)
    export_catalogue_xlsx(db, tmp_path / "c.xlsx", box.id)
    rows = read_xlsx(tmp_path / "c.xlsx")[0]["Faltantes"][3:]
    assert [r[1] for r in rows] == ["Pleito A"]
    assert "faltan IMG_002" in rows[0][11]


def test_authority_sheets_print_the_graphs_fields_beside_each_distinct_value(db, tmp_path):
    box = _box(db)
    export_catalogue_xlsx(db, tmp_path / "c.xlsx", box.id)
    sheets = read_xlsx(tmp_path / "c.xlsx")[0]
    assert sheets["Personas"][2] == ["Mora, Ana", "Ana", "Mora", "", "confirmado", "Pleito A", ""]
    assert sheets["Lugares"][2] == ["Villa Sur", "Villa Sur", "pueblo", "", "propuesto", "Pleito A", ""]
    assert sheets["Entidades"][2] == ["Juzgado", "", "propuesto", "Pleito A", ""]


def test_proposals_omitted_leaves_unconfirmed_names_out(db, tmp_path):
    box = _box(db)
    export_catalogue_xlsx(db, tmp_path / "c.xlsx", box.id, proposals="omitted")
    sheets = read_xlsx(tmp_path / "c.xlsx")[0]
    assert len(sheets["Lugares"]) == 2 and len(sheets["Personas"]) == 3
    assert [r[0] for r in sheets["Nombres"][1:]] == ["Mora, Ana"]


def test_nombres_marks_a_spacy_only_name_and_says_who_made_it(db, tmp_path):
    box = _box(db)
    export_catalogue_xlsx(db, tmp_path / "c.xlsx", box.id)
    names = read_xlsx(tmp_path / "c.xlsx")[0]["Nombres"]
    assert names[1][:5] == ["Mora, Ana", "", "person", "confirmado", "Pleito A"]
    assert names[2][:5] == ["Villa Sur", "", "location", "propuesto (spaCy)", "Pleito A"] and names[2][5] == "spaCy"


def test_catalogo_paginas_declaraciones_and_notas(db, tmp_path):
    box = _box(db)
    export_catalogue_xlsx(db, tmp_path / "c.xlsx", box.id)
    sheets = read_xlsx(tmp_path / "c.xlsx")[0]
    head = sheets["Catálogo"][0]
    assert head.index("catalogue_date_normalised") == head.index("catalogue_dates") + 1
    assert [r[:2] for r in sheets["Páginas"][1:]] == [["Pleito A", "IMG_001"], ["Pleito A", "IMG_003"]]
    assert sheets["Declaraciones"][1] == ["Ana", "demandó", "a Pedro", "", "Ana demandó a Pedro"]
    assert sheets["Notas"][1][:7] == ["Pleito A", "catalogue_title", "Fichero (m-1)", "catalogue", "r1", "", "el título"]
    assert not any(r[1] == "folder_name" for r in sheets["Notas"])


def test_csv_is_one_file_per_sheet_with_a_bom_every_field_quoted_and_crlf(db, tmp_path):
    box = _box(db)
    result = export_catalogue_xlsx(db, tmp_path / "c", box.id, file_format="csv")
    assert result.output_path.endswith(".zip") and result.sheets == ORDER
    with zipfile.ZipFile(result.output_path) as z:
        assert sorted(z.namelist()) == sorted(f"{n}.csv" for n in ORDER)
        raw = z.read("Tema.csv")
    assert raw.startswith(b"\xef\xbb\xbf\"Related Subjects\",\"Tema\"\r\n")
    assert "Pleito por una finca" in zipfile.ZipFile(result.output_path).read("Catálogo.csv").decode("utf-8-sig")


def test_the_unit_helpers_agree_with_the_sheet(db):
    box = _box(db)
    assert [f.name for f in sheet.folders_under(db, box)][:2] == ["Caja 12", "Pleito A"]
