"""catalogue.export.template-is-the-prototype and one-sheet-per-collection (catalogue-export.md, step 1.5/2.1)."""
from fichero_server.export_service import export_catalogue_xlsx
from fichero_server.models.knowledge import ClassificationDimension, ClassificationValue
from tests.unit.export.helpers import folder, page, read_xlsx


def _proto(db, key, attrs, parent=None):
    db.save(ClassificationValue(dimension=ClassificationDimension.document_prototype, key=key, label=key,
                                parent_key=parent, attributes=attrs))


def _protos(db):
    _proto(db, "tbase", {
        "folder_name": {"type": "text", "order": 1, "source": "folder.name", "labels": {"es": "Nombre", "en": "Name"}},
        "title": {"type": "text", "order": 2, "labels": {"es": "Título", "en": "Title"}, "help": {"es": "Escriba"}},
        "n": {"type": "number", "order": 3, "source": "folder.page_count", "labels": {"es": "Cuenta"}},
    })
    _proto(db, "tletter", {"sender": {"type": "text", "order": 4, "labels": {"es": "Remitente"}}}, parent="tbase")
    _proto(db, "tbox", {"subfolders": "tbase"})


def _export(db, tmp_path, target=None, **kw):
    out = tmp_path / "c.xlsx"
    export_catalogue_xlsx(db, out, target, **kw)
    return read_xlsx(out)


def test_one_kind_gives_its_columns_with_three_frozen_header_rows(db, tmp_path):
    _protos(db)
    box = folder(db, "Caja 1", proto="tbox")
    f = folder(db, "Carta uno", box.id, attrs={"title": "Una carta"}, seq=1)
    page(db, "IMG_001.jpg", f.id, seq=1)
    page(db, "IMG_002.jpg", f.id, seq=2)
    sheets, frozen = _export(db, tmp_path, box.id)
    name = "Caja 1 Catalogación básica"
    assert list(sheets)[0] == name and "Tema" in sheets
    assert frozen[name] == 3
    assert sheets[name] == [["Name", "Title", ""], ["Nombre", "Título", "Cuenta"], ["", "Escriba", ""],
                            ["Carta uno", "Una carta", "2"]]


def test_mixed_kinds_show_the_union_each_row_filling_its_own(db, tmp_path):
    _protos(db)
    scope = folder(db, "Scope")
    folder(db, "A", scope.id, proto="tletter", attrs={"sender": "X"}, seq=1)
    folder(db, "B", scope.id, proto="tbase", attrs={"title": "T"}, seq=2)
    sheets, _ = _export(db, tmp_path, scope.id)
    rows = sheets["Scope Catalogación básica"]
    assert rows[1][:4] == ["Nombre", "Título", "Cuenta", "Remitente"]
    assert rows[3] == ["A", "", "0", "X"] and rows[4] == ["B", "T", "0", ""]


def test_no_prototype_gives_every_catalogue_key_alphabetically_with_the_key_as_header(db, tmp_path):
    scope = folder(db, "Scope")
    folder(db, "A", scope.id, attrs={"catalogue_title": "T", "catalogue_abc": "z", "other": "o"})
    sheets, frozen = _export(db, tmp_path, scope.id)
    assert sheets["Scope Catalogación básica"] == [["catalogue_abc", "catalogue_title"], ["z", "T"]]
    assert frozen["Scope Catalogación básica"] == 1


def test_a_named_prototype_overrides_and_a_saved_choice_narrows(db, tmp_path):
    _protos(db)
    scope = folder(db, "Scope", meta={"column_choice": {"hide": ["n"]}})
    folder(db, "A", scope.id, proto="tletter", attrs={"sender": "X"})
    sheets, _ = _export(db, tmp_path, scope.id)
    assert sheets["Scope Catalogación básica"][1] == ["Nombre", "Título", "Remitente"]
    out = tmp_path / "d.xlsx"
    export_catalogue_xlsx(db, out, scope.id, prototype_key="tbase")
    assert read_xlsx(out)[0]["Scope Catalogación básica"][1] == ["Nombre", "Título", "Cuenta"]


def test_a_box_of_collections_writes_one_sheet_each(db, tmp_path):
    _protos(db)
    project = folder(db, "P")
    for n in ("C1", "C2"):
        c = folder(db, n, project.id, proto="tbox")
        folder(db, f"{n} doc", c.id)
    sheets, _ = _export(db, tmp_path, project.id)
    assert list(sheets)[:3] == ["C1 Catalogación básica", "C2 Catalogación básica", "Faltantes"]
    assert sheets["C2 Catalogación básica"][-1][0] == "C2 doc"
