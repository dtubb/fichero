"""catalogue.export.one-row-per-folder and cells-from-attributes-never-guessed (catalogue-export.md step 1.3)."""
from fichero_server.export_service import export_catalogue_xlsx
from tests.unit.export.helpers import folder, page, read_xlsx

NAME = "Caja Catalogación básica"


def _rows(db, tmp_path, scope):
    export_catalogue_xlsx(db, tmp_path / "c.xlsx", scope.id)
    return read_xlsx(tmp_path / "c.xlsx")[0][NAME][3:]


def test_a_folder_comes_first_and_its_subfolders_after_in_sidebar_order(db, tmp_path):
    box = folder(db, "Caja", proto="eap_box")
    second = folder(db, "Doc 10", box.id, seq=2)
    first = folder(db, "Doc 2", box.id, seq=1)
    folder(db, "Parte b", first.id, seq=2)
    folder(db, "Parte a", first.id, seq=1)
    assert [r[1] for r in _rows(db, tmp_path, box)] == ["Doc 2", "Parte a", "Parte b", "Doc 10"]
    assert second.id


def test_fact_columns_come_from_the_folder_and_its_pages_alone(db, tmp_path):
    box = folder(db, "Caja", proto="eap_box")
    f = folder(db, "Doc", box.id)
    page(db, "scan-9.jpg", f.id, meta={"source_filename": "IMG_0009.tif"}, seq=1)
    page(db, "IMG_0010.jpg", f.id, seq=2)
    empty = folder(db, "Vacío", box.id)
    row, blank = _rows(db, tmp_path, box)
    assert row[1:5] == ["Doc", "IMG_0009", "IMG_0010", "2"]
    assert blank[1:5] == ["Vacío", "", "", "0"] and empty.id


def test_a_cell_is_the_effective_value_own_else_inherited_never_guessed(db, tmp_path):
    box = folder(db, "Caja", proto="eap_box", attrs={"catalogue_original_reference": "Archivo Z"})
    folder(db, "Con", box.id, seq=1, attrs={"catalogue_original_reference": "Propia", "catalogue_title": "T"})
    folder(db, "Sin", box.id, seq=2)
    own, inherited = _rows(db, tmp_path, box)
    assert own[5:7] == ["T", "Propia"] and inherited[5:7] == ["", "Archivo Z"]
    assert inherited[7:] == ["", "", "", "", "", ""]  # nothing invented: date, places, people, description, problems, subjects


def test_people_print_by_the_declarations_name_order_from_the_entitys_names(db, tmp_path):
    from fichero_server.models.knowledge import EntityType, KnowledgeEntity

    db.save(KnowledgeEntity(canonical_name="Ana Mora", entity_type=EntityType.person,
                            metadata={"given_names": "Ana", "surnames": "Mora"}))
    db.save(KnowledgeEntity(canonical_name="Fray Luis", entity_type=EntityType.person, metadata={"given_names": "Luis"}))
    box = folder(db, "Caja", proto="eap_box")
    folder(db, "Carta", box.id, seq=1, attrs={"catalogue_people": ["Ana Mora", "Fray Luis", "Pedro Luna"]})
    out = tmp_path / "c.xlsx"
    export_catalogue_xlsx(db, out, box.id)
    rows = read_xlsx(out)[0]["Caja Catalogación básica"]
    assert "Mora, Ana|Fray Luis|Pedro Luna" in rows[3]  # a split name by surname first; the rest as written
