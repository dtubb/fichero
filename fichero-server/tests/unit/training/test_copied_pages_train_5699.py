"""A copied page's photograph is found by the training set, and a start with nothing to train on is refused up
front with the preview's reason (#5699), tested to the spec: `compute.tune.set-excludes-flagged-lines`
(docs/contributor_manual/specs/compute/jobs-and-fine-tuning.md).

WHY: the overnight MCP walk (2026-10-11): the preview listed 86 copy-imported pages as "its photograph is not on
this Mac" (the set read the stored path, `files/11_/…JPG`, as it stands, not inside the package), and a start
on that empty set was accepted, then failed a second later with another reason.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PIL import Image

from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.training.kraken_set import build_training_set
from tests.unit.training.test_kraken_training_set import TEACHER, _page

pytestmark = pytest.mark.usefixtures("project_says_yes")  # the project says yes to cloud models (review 672)


def _copied(db, tmp_path, folder: Document) -> Document:
    """A page as a copy-import stores it: its photograph inside the package, its path relative to it."""
    page = _page(db, tmp_path, "11_Hoja_540_Recto", folder)
    inside = Path("files") / "11" / "11_Hoja_540_Recto.jpg"
    (Path(db.path).parent / inside).parent.mkdir(parents=True, exist_ok=True)
    shutil.move(page.path, Path(db.path).parent / inside)
    page.path = str(inside)
    db.save(page)
    return page


@pytest.fixture
def folder(db):
    made = Document(name="CACIQUES", doc_type=DocType.folder)
    db.save(made)
    return made


def test_a_copied_pages_photograph_is_found_inside_the_package(db, tmp_path, folder):
    page = _copied(db, tmp_path, folder)
    made = build_training_set(db, scope_ids=[folder.id], teacher=TEACHER, held_out_ids=[], out_dir=None)
    assert [p.document_id for p in made.pages] == [page.id], made.missing


def test_a_start_with_nothing_to_train_on_is_refused_with_the_previews_reason(db, client, tmp_path, folder):
    photo = tmp_path / "unread.jpg"
    Image.new("RGB", (40, 30)).save(photo)
    db.save(Document(name="unread.jpg", doc_type=DocType.file, file_type=FileType.image, path=str(photo),
                     parent_id=folder.id, status=Status.completed))
    preview = client.get("/api/training/set", params={"teacher": TEACHER, "scope_ids": [folder.id]}).json()
    assert preview["pages"] == 0
    (why,) = {m["why"] for m in preview["missing"]}

    r = client.post("/api/training/kraken/here", json={"scope_ids": [folder.id], "teacher": TEACHER, "epochs": 1})
    assert r.status_code == 422 and why in r.json()["detail"], r.text

    # On Hugging Face too, after its own refusals (the yes, the token): checked with a stand-in for the Hub.
    from fichero_server.models.compute_requests import TrainKrakenRequest
    from fichero_server.training import job as training_job
    from fichero_server.training.kraken_set import EmptyTrainingSet
    from tests.unit.training.test_training_job import NOTEBOOK_FLAVOR, FakeHub

    request = TrainKrakenRequest(scope_ids=[folder.id], teacher=TEACHER, flavor=NOTEBOOK_FLAVOR, pages_may_leave=True)
    with pytest.raises(EmptyTrainingSet, match=why):
        training_job.start(db, request, started_by="historian", target_factory=FakeHub)
    assert not db.execute_fetchall("SELECT id FROM jobs WHERE kind IN ('train-on-this-mac', 'train-a-model')")
