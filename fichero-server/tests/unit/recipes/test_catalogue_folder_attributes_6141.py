"""The Catalogue stage's labelled fields also become the folder's attributes (#6141, `catalogue.folder-description-fields`),
through the existing attribute path: typed, citing the run, a person's own value never overwritten."""
from __future__ import annotations

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.models import DocType, Document
from fichero_server.recipes import catalogue_step
from fichero_server.workflows import attribute_sources as sources

CONFIG = LLMConfig(provider="fake", model="fake")
TEXT = ("Title: Wheat letters.\nDates: 12 March 1776 to 3 May 1780.\nExtent: 2 pages.\n"
        "Creator and hands: Ana Ruiz; one clerk's hand.\nScope and content: Letters about wheat.\n"
        "Language and script: Spanish, secretary hand.\nCondition: [ilegible] on page 2.\n"
        "Access points: Ana Ruiz; Sevilla; Casa de Contratación.\nDescription: A short paragraph.")


@pytest.fixture
def said(monkeypatch):
    answer = {"text": TEXT}

    async def fake(material, config, system=None, permissive_guardrails=False):
        return answer["text"]

    monkeypatch.setattr("fichero_server.llm.chat_with_fallback", fake)
    return answer


def _folder(db):
    box = Document(name="Box 1", doc_type=DocType.folder)
    db.save(box)
    pages = []
    for i in range(2):
        page = Document(name=f"p{i}", doc_type=DocType.page, parent_id=box.id, page_content=f"Letter {i} about wheat")
        db.save(page)
        pages.append(page.id)
    return box.id, pages


def test_the_fields_are_parsed_typed_with_iso_years():
    got = catalogue_step.parse_fields(TEXT)
    assert got["catalogue_title"] == "Wheat letters."
    assert got["catalogue_dates"] == "12 March 1776 to 3 May 1780."
    assert (got["catalogue_date_start"], got["catalogue_date_end"]) == ("1776", "1780")
    assert got["catalogue_creators"] == ["Ana Ruiz", "one clerk's hand"]
    assert got["catalogue_access_points"] == ["Ana Ruiz", "Sevilla", "Casa de Contratación"]
    assert "Scope and content" not in str(got) and "Letters about wheat" not in str(got)  # prose stays in the content


def test_a_field_the_text_lacks_is_not_written_and_no_year_means_no_iso_dates():
    got = catalogue_step.parse_fields("Title: A box.\nDates: undated.\nScope and content: x.")
    assert got == {"catalogue_title": "A box.", "catalogue_dates": "undated."}


def test_after_the_stage_runs_the_folder_has_the_attributes_citing_the_run(db, said):
    box, pages = _folder(db)
    catalogue_step.describe_folders(db, pages, CONFIG, run_id="run-1")
    folder = db.get(Document, box)
    assert folder.attributes["catalogue_title"] == "Wheat letters."
    assert folder.attributes["catalogue_date_start"] == "1776" and folder.attributes["catalogue_access_points"][1] == "Sevilla"
    source = sources.sources(folder)["catalogue_extent"]
    assert source["by"] == "machine" and source["run_id"] == "run-1" and source["artifact_id"]
    assert "Letters about wheat" in folder.page_content  # the prose is still the content


def test_a_value_a_person_set_is_unchanged_and_a_rerun_replaces_only_the_runs_own(db, said):
    box, pages = _folder(db)
    folder = db.get(Document, box)
    folder.attributes = {"catalogue_title": "My own title"}
    folder.metadata = sources.with_sources(folder.metadata, {"catalogue_title": {"by": "person"}})
    db.save(folder)
    catalogue_step.describe_folders(db, pages, CONFIG, run_id="run-1")
    folder = db.get(Document, box)
    assert folder.attributes["catalogue_title"] == "My own title" and folder.attributes["catalogue_extent"] == "2 pages."
    # New pages change the coverage: the folder is described again, now without Extent.
    new = Document(name="p9", doc_type=DocType.page, parent_id=box, page_content="Another letter")
    db.save(new)
    said["text"] = TEXT.replace("Extent: 2 pages.\n", "")
    catalogue_step.describe_folders(db, pages + [new.id], CONFIG, run_id="run-2")
    folder = db.get(Document, box)
    assert "catalogue_extent" not in folder.attributes  # the run's own value that the new description no longer has
    assert folder.attributes["catalogue_title"] == "My own title"


@pytest.mark.parametrize("dates,start,end", [
    ("1850-60", "1850", "1860"), ("1850\u201360", "1850", "1860"), ("1850/60", "1850", "1860"),
    ("1899-01", "1899", "1901"), ("1850-1860", "1850", "1860"), ("1776, 1780 and 1779", "1776", "1780"),
])
def test_a_short_end_of_a_range_is_read_as_the_year_it_ends(dates, start, end):
    got = catalogue_step.parse_fields(f"Dates: {dates}")
    assert (got["catalogue_date_start"], got["catalogue_date_end"]) == (start, end)


def test_creators_are_split_at_the_semicolons_the_prompt_asks_for():
    from pathlib import Path

    prompt = (Path(catalogue_step.__file__).parent.parent / "resources/prompts/catalogue/folder_description_v2.md").read_text()
    assert "records name or the facts give, separated by semicolons" in " ".join(prompt.split())
    assert catalogue_step.parse_fields("Creator and hands: Ana Ruiz, scribe; Luis Pérez")["catalogue_creators"] == [
        "Ana Ruiz, scribe", "Luis Pérez"]
