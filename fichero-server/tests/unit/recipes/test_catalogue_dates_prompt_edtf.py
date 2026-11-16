"""catalogue.export.dates-prompt-returns-edtf (#6282, #6270): the next prompt version asks for EDTF beside the text; shipped
versions stay; the model's EDTF lands as a machine proposal citing the run, the model and the words; a described folder is not rerun."""
from __future__ import annotations

from pathlib import Path

from fichero_server.llm.prompts import get_prompt, list_versions
from fichero_server.models import Artifact, DocType, Document
from fichero_server.recipes import catalogue_step as step
from fichero_server.workflows import attribute_sources as sources

TEXT = ("Title: Cartas.\nDates: a los ocho días del mes de mayo de mil novecientos nueve.\n"
        "Dates EDTF: 1909-05-08 [a los ocho días del mes de mayo de mil novecientos nueve]\nScope and content: Cartas.")


def test_v4_asks_for_edtf_and_the_stage_uses_it_and_v3_is_unchanged():
    assert list_versions("catalogue", "folder_description")[-1] == 4
    v4 = get_prompt("catalogue", "folder_description", version=4).render(output_language="Spanish", max_words=500)
    assert "Dates EDTF:" in v4 and "the words of the records you read it from" in " ".join(v4.split())
    v3 = get_prompt("catalogue", "folder_description", version=3).render(output_language="Spanish", max_words=500)
    assert "EDTF" not in v3
    assert 'version=4' in Path(step.__file__).read_text()


def test_the_edtf_line_ends_the_dates_field_and_is_no_attribute():
    got = step.parse_fields(TEXT)
    assert got["catalogue_dates"] == "a los ocho días del mes de mayo de mil novecientos nueve."
    assert "EDTF" not in str(got.get("catalogue_scope_content")) and "catalogue_dates_edtf" not in got


def test_model_date_reads_the_value_and_its_words_and_refuses_what_is_no_edtf():
    assert step.model_date(TEXT) == ("1909-05-08", "a los ocho días del mes de mayo de mil novecientos nueve")
    assert step.model_date("Dates EDTF: 1909-05-08/1910-02?") == ("1909-05-08/1910-02?", "")
    assert step.model_date("Dates EDTF: mayo 1909") is None
    assert step.model_date("Dates: 1909") is None


def test_the_answer_lands_with_the_run_the_model_and_the_words(db):
    folder = Document(name="Box", doc_type=DocType.folder)
    db.save(folder)
    art = Artifact(document_id=folder.id, artifact_type=step.ARTIFACT_TYPE, content=TEXT, provider="p", model="m")
    db.save(art)
    step.put_in_attributes(db, folder.id, TEXT, art.id, run_id="r1", provider="p", model="m")
    doc = db.get(Document, folder.id)
    source = sources.sources(doc)["catalogue_date_normalised"]
    assert doc.attributes["catalogue_date_normalised"] == "1909-05-08"
    assert (source["by"], source["run_id"], source["model"]) == ("machine", "r1", "m")
    assert source["cites"] == {"kind": "words", "words": "a los ocho días del mes de mayo de mil novecientos nueve"}
