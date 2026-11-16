"""catalogue.export.dates-in-the-archives-format (catalogue-export.md step 1.3): the start side of the EDTF, at its precision."""
from fichero_server import catalogue_sheet as sheet
from fichero_server.models.prototype_template import template_for_prototype


def test_a_year_renders_as_a_year_and_marks_are_dropped(db):
    col = next(c for c in template_for_prototype(db, "eap_digital_folder") if c.key == "catalogue_date_normalised")
    assert sheet.render_date("1892", col) == "1892"
    assert sheet.render_date("1892-03~", col) == "Marzo/1892"
    assert sheet.render_date("1892-03-05?/1893", col) == "5/Marzo/1892"
    assert sheet.render_date("", col) == "" and sheet.render_date("no es fecha", col) == ""




def test_the_month_names_come_from_the_declaration_not_the_code(db):
    col = next(c for c in template_for_prototype(db, "eap_digital_folder") if c.key == "catalogue_date_normalised")
    assert sheet.render_date("1892-03-17", col, "en") == "17/March/1892"
