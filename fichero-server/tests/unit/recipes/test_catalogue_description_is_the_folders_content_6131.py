"""#6131 (`catalogue.folder-description-fields`): the Catalogue stage's description is the folder's content, so selecting
the folder shows it and search and export read it; a person's own content stays; the artifact stays as the run's record."""
from __future__ import annotations

from fichero_server.models import Artifact, Document
from fichero_server.recipes import catalogue_step
from fichero_server.workflows.curation_guard import PAGE_CONTENT_USER_EDITED_KEY

from tests.unit.recipes.test_catalogue_stage_6087 import CONFIG, _tree, asked  # noqa: F401

DESCRIPTION = "Title: A box.\nScope and content: Letters about wheat."


def test_a_folder_with_no_content_gets_the_description_as_its_content(db, asked):  # noqa: F811
    top, box, pages = _tree(db)
    catalogue_step.describe_folders(db, pages, CONFIG, run_id=None)
    for folder in (box, top):
        assert db.get(Document, folder).page_content == DESCRIPTION
    assert [a for a in db.query(Artifact, document_id=box) if a.artifact_type == catalogue_step.ARTIFACT_TYPE], \
        "the artifact stays as the run's record"


def test_content_a_person_wrote_stays_the_content(db, asked):  # noqa: F811
    top, box, pages = _tree(db)
    folder = db.get(Document, box)
    folder.page_content = "My own note on this box"
    db.save(folder)
    catalogue_step.describe_folders(db, pages, CONFIG, run_id=None)
    assert db.get(Document, box).page_content == "My own note on this box"
    assert db.get(Document, top).page_content == DESCRIPTION, "the other folder is still given its description"


def test_content_a_person_edited_after_the_description_stays_over_a_rerun(db, asked):  # noqa: F811
    top, box, pages = _tree(db)
    catalogue_step.describe_folders(db, pages, CONFIG, run_id=None)
    folder = db.get(Document, box)
    folder.page_content = "Corrected by hand"
    folder.metadata = {**(folder.metadata or {}), PAGE_CONTENT_USER_EDITED_KEY: True}
    db.save(folder)
    page = db.get(Document, pages[0])
    page.page_content = "Letter 0, read again"
    db.save(page)
    catalogue_step.describe_folders(db, pages, CONFIG, run_id=None)
    assert db.get(Document, box).page_content == "Corrected by hand"


def test_a_rerun_replaces_its_own_earlier_description(db, asked, monkeypatch):  # noqa: F811
    top, box, pages = _tree(db)
    catalogue_step.describe_folders(db, pages, CONFIG, run_id=None)
    page = db.get(Document, pages[0])
    page.page_content = "Letter 0, read again by another reader"
    db.save(page)

    async def fresh(material, config, system=None, permissive_guardrails=False):
        return "Title: A box, redone.\nScope and content: Letters about rye."

    monkeypatch.setattr("fichero_server.llm.chat_with_fallback", fresh)
    catalogue_step.describe_folders(db, pages, CONFIG, run_id=None)
    assert db.get(Document, box).page_content.startswith("Title: A box, redone.")


def test_the_open_migration_does_not_wipe_the_description_the_stage_wrote(db, asked):  # noqa: F811
    """The #5599 migration runs at every project open and clears a folder whose text equals its catalogue.narrative
    artifact (the old workflow's leftover). The stage writes exactly that on purpose (#6131), so it must be skipped."""
    from fichero_server.db.migrations.runner import move_catalogue_narratives_on_open

    top, box, pages = _tree(db)
    catalogue_step.describe_folders(db, pages, CONFIG, run_id=None)
    assert db.get(Document, box).page_content == DESCRIPTION

    move_catalogue_narratives_on_open(db)

    assert db.get(Document, box).page_content == DESCRIPTION
    assert db.get(Document, top).page_content == DESCRIPTION


def test_the_migration_still_clears_the_old_workflows_leftover(db):
    """A folder whose text equals a narrative artifact but that the stage did not mark is the old behaviour's leftover."""
    from fichero_server.db.migrations.runner import move_catalogue_narratives_on_open

    folder = Document(name="Old", doc_type=catalogue_step_doc_type(), page_content=DESCRIPTION)
    db.save(folder)
    db.save(Artifact(document_id=folder.id, artifact_type=catalogue_step.ARTIFACT_TYPE, content=DESCRIPTION, data={}))
    move_catalogue_narratives_on_open(db)
    assert not (db.get(Document, folder.id).page_content or "").strip()


def catalogue_step_doc_type():
    from fichero_server.models import DocType

    return DocType.folder
