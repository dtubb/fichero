"""proto.shipped.eap-prototypes (attributes-and-prototypes.md Step 1.3)."""

import json

import pytest

from fichero_server.db import Database
from fichero_server.models.knowledge import ClassificationDimension, ClassificationValue
from fichero_server.models.prototype_schema import attribute_declarations, ordered_field_keys
from fichero_server.models.prototype_template import template_for_prototype
from fichero_server.models.shipped_prototypes import shipped_prototypes


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "t.duckdb")
    yield d
    d.close()


def _get(db, key):
    return next(v for v in db.query(ClassificationValue, dimension=ClassificationDimension.document_prototype)
                if v.key == key)


def test_the_three_eap_prototypes_load_read_only_on_open(db):
    for key in ("eap_box", "eap_digital_folder", "eap_digital_folder_en"):
        assert _get(db, key).is_builtin is True


def test_eap_digital_folder_is_the_thirteen_columns_in_order(db):
    cols = template_for_prototype(db, "eap_digital_folder")
    assert [c.labels.get("es") or c.labels.get("en") for c in cols][:2] == ["Tu nombre", "Nombre de carpeta digital"]
    assert [c.key for c in cols] == [
        "cataloguer", "folder_name", "first_file", "last_file", "page_count", "catalogue_title",
        "catalogue_original_reference", "catalogue_date_normalised", "catalogue_places",
        "catalogue_people", "description", "problems", "catalogue_subjects"]
    by = {c.key: c for c in cols}
    assert by["catalogue_places"].join == "|" and by["catalogue_people"].join == "|"
    assert by["catalogue_people"].name_order == "surname_first"
    assert by["catalogue_original_reference"].inherits is True
    assert by["catalogue_date_normalised"].format == "d/Mes/aaaa"
    assert by["catalogue_date_normalised"].months["es"][2] == "Marzo"
    assert by["cataloguer"].source == "cataloguer" and by["cataloguer"].kind == "computed"
    assert all(c.help.get("es") for c in cols)  # an instruction line per column


def test_tema_defaults_to_the_teams_subject_list_and_stays_editable(db):
    subjects = {c.key: c for c in template_for_prototype(db, "eap_digital_folder")}["catalogue_subjects"]
    assert subjects.type == "multi_select" and "Indigenous populations" in subjects.options
    assert set(subjects.option_labels["en"]) == set(subjects.options)
    assert set(subjects.option_labels["es"]) <= set(subjects.options)  # Spanish only where the team gave it
    assert subjects.option_labels["es"]["Commerce"] == "comercio"


def test_funders_row_one_labels_exist_where_the_funder_has_a_heading(db):
    by = {c.key: c for c in template_for_prototype(db, "eap_digital_folder")}
    assert by["folder_name"].labels["en"] == "Digital Folder Name"
    assert by["catalogue_date_normalised"].labels["en"] == "Dates of Material (Gregorian Calendar)"
    assert "en" not in by["catalogue_people"].labels  # the funder has no heading for it


def test_english_variant_is_the_funders_nine_columns_one_label_language(db):
    cols = template_for_prototype(db, "eap_digital_folder_en")
    assert len(cols) == 9
    assert all(set(c.labels) == {"en"} for c in cols)


def test_box_names_the_folder_kind_and_the_reference_inherits(db):
    from fichero_server.models.node_prototypes import resolve_prototype_attributes
    from fichero_server.models.prototype_schema import level_defaults

    attrs = resolve_prototype_attributes(db, "eap_box")
    assert level_defaults(attrs) == {"subfolders": "eap_digital_folder"}
    assert attribute_declarations(attrs)["catalogue_original_reference"].inherits is True
    assert level_defaults(resolve_prototype_attributes(db, "eap_digital_folder")) == {"pages": "eap_page"}


def test_a_changed_shipped_file_migrates_forward_by_key_on_open(tmp_path):
    path = tmp_path / "t.duckdb"
    d = Database(path)
    row = _get(d, "eap_page")
    row.label = "stale label"
    row.attributes = {"old": "x"}
    d.save(row)
    d.close()
    d = Database(path)
    try:
        fresh = _get(d, "eap_page")
        shipped = {p["key"]: p for p in shipped_prototypes()}["eap_page"]
        assert fresh.label == shipped["label"] and fresh.attributes == shipped["attributes"]
    finally:
        d.close()


def test_a_projects_own_prototype_with_a_shipped_key_is_left_alone(tmp_path):
    path = tmp_path / "t.duckdb"
    d = Database(path)
    d.save(ClassificationValue(dimension=ClassificationDimension.document_prototype, key="mine", label="mine",
                               attributes={"x": {"type": "text"}}, is_builtin=False))
    d.close()
    d = Database(path)
    try:
        assert _get(d, "mine").attributes == {"x": {"type": "text"}}
    finally:
        d.close()


def test_every_shipped_file_is_valid_json_with_valid_declarations():
    found = shipped_prototypes()
    assert {"eap_box", "eap_digital_folder", "eap_digital_folder_en", "eap_page"} <= {p["key"] for p in found}
    for proto in found:
        assert attribute_declarations(proto["attributes"]) is not None
        assert ordered_field_keys(proto["attributes"]) is not None
        assert json.loads(json.dumps(proto)) == proto
