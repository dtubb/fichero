"""#5906: a copy never writes on the source project (the owner's rule: a copy keeps its author, the original is untouched).

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md (`source.copy.source-is-read-only`,
`source.copy.copy-into-project-is-not-a-copy-between-projects`). Two real open projects, through the real routes: every
source page keeps its row, path, metadata and timestamps; `copy_into_project` called on the target never touches a
page that belongs to the source.
"""

from __future__ import annotations

from fichero_server.api.main import app
from fichero_server.db.manager import db_manager
from fichero_server.models import Artifact, Document, ReadingChoice, Segment, SegmentPass

from tests.unit.transfer._two_projects import build_box, header_decides, open_source, table_counts


def _documents(db) -> dict[str, dict]:
    """Every Document row of a project, whole (id -> its dump): path, metadata and timestamps included."""
    return {d.id: d.model_dump(mode="json") for d in db.all(Document)}


def _derived(db) -> dict[str, dict]:
    """What a person made on the pages, whole: passes, lines, readings, artifacts (a copy must not rewrite them either)."""
    return {f"{model.__name__}:{row.id}": row.model_dump(mode="json")
            for model in (SegmentPass, Segment, ReadingChoice, Artifact) for row in db.all(model)}


def test_a_transfer_leaves_every_source_page_identical(client, db, tmp_path):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    before, counts, made = _documents(source), table_counts(source), _derived(source)
    assert made, "the box has passes and lines to compare"

    response = client.post("/api/documents/transfer", json={"items": [box.folder.id], "source": str(source_package)})
    assert response.status_code == 200, response.text

    assert _documents(source) == before, "a source page's row, path, metadata or timestamp changed"
    assert table_counts(source) == counts, "the source gained or lost a row other than the transfer's journal"
    assert _derived(source) == made, "a source pass, line, reading or artifact changed"


def test_copy_into_project_on_the_target_never_touches_the_sources_pages(client, db, tmp_path):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    before = _documents(source)

    # r1's reading: "copy these pages into the project", with the SOURCE's page ids, on the target project
    header_decides(app)  # the library header picks the target, as in the app
    response = client.post("/api/documents/copy-into-project", json={"ids": [box.page1.id, box.page2.id]})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["copied"] == {}, "no page of another project is copied"
    assert set(body["not_copied"]) == {box.page1.id, box.page2.id}
    assert all("no such page in this project" in why for why in body["not_copied"].values())
    assert _documents(source) == before, "the source was written by a copy into the target"
