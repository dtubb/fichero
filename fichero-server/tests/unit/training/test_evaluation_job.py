"""The evaluation job (#5441, `distill.eval.*`), tested to the spec through the public routes.

A trained reader is only worth keeping if it beats what can be downloaded. The job reads the held-out
pages (checked, never trained on) with the trained reader and the out-of-the-box readers on this Mac,
scores each with Fichero's one CER under every normalisation policy, and writes the scores on each
model's card.

Everything goes through `GET /api/training/set`, `POST /api/evaluation/runs`, the job as the scheduler
runs it (`jobs.KINDS["evaluate-models"].run`), `GET /api/evaluation/runs/{id}` and
`GET /api/evaluation/scores`. Kraken is faked at its seam (`kraken_runtime.read_given_lines`): no torch,
no model, no training, nothing downloaded.
"""
from __future__ import annotations

import json

import pytest

from fichero_server.execution import jobs
from fichero_server.llm import kraken_runtime
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import SegmentPass
from fichero_server.training import evaluation
from fichero_server.training.landing import land_trained_reader
from fichero_server.workflows import transcription_accuracy
from tests.unit.training.test_kraken_training_set import BOOT, PAGE, TEACHER, _page

CHECKED = "anthropic/fable-checked"
BASE = "kraken-mccatmus"


@pytest.fixture(autouse=True)
def homes(tmp_path, monkeypatch):
    """Kraken's readers and the MLX store in the test's own folders, never this Mac's."""
    from fichero_server.llm import mlx_model_store

    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken-data"))
    store = mlx_model_store.MLXModelStore(tmp_path / "mlx")
    monkeypatch.setattr(mlx_model_store, "get_mlx_model_store", lambda: store)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)  # the test runs the job itself


class Readers:
    """Kraken's reader, faked at the seam. The trained reader reads every line as checked; the base
    reader drops each line's last character. Records which photograph each reader was given."""

    def __init__(self, trained_path: str):
        self.trained_path = trained_path
        self.read: dict[str, list[str]] = {}

    def __call__(self, image_path, model_path, lines, **kw):
        self.read.setdefault(str(model_path), []).append(str(image_path))
        if model_path == self.trained_path:
            return [ln["text"] for ln in lines]
        return [ln["text"][:-1] for ln in lines]


def _checked(db, tmp_path, doc: Document, *, by_a_person: bool) -> SegmentPass:
    """A second pass on the page, checked: Fable's (a model) or a person's. (The same lines in a file of its
    own: one file is imported onto a page once.)"""
    from fichero_server.actions.registry import registry

    checked_file = tmp_path / "checked.page.xml"
    checked_file.write_bytes(PAGE.read_bytes() + b"\n<!-- checked -->\n")
    before = {p.id for p in db.query(SegmentPass, document_id=doc.id)}
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(checked_file)}, BOOT)
    (made,) = [p for p in db.query(SegmentPass, document_id=doc.id) if p.id not in before]
    made.model = CHECKED
    if by_a_person:
        made.provenance_kind = ProvenanceKind.human
    db.save(made)
    return made


@pytest.fixture
def project(db, tmp_path):
    folder = Document(name="SM_NPQ_C01", doc_type=DocType.folder)
    db.save(folder)
    taught = _page(db, tmp_path, "SM_NPQ_C01_001", folder)
    held = [_page(db, tmp_path, f"SM_NPQ_C01_00{i}", folder) for i in (2, 3)]
    _checked(db, tmp_path, held[0], by_a_person=True)
    _checked(db, tmp_path, held[1], by_a_person=False)
    return {"folder": folder, "taught": taught, "held": held}


def _base_installed(tmp_path) -> str:
    weights = tmp_path / "mccatmus.mlmodel"
    weights.write_bytes(b"stock weights")
    marker = kraken_runtime._marker_path(BASE)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"model_path": str(weights)}), encoding="utf-8")
    return str(weights)


def _trained(client, tmp_path, project, *, held_out: list[str], job: str = "0f4e2a6c-1111-2222-3333-444455556666") -> str:
    """A reader landed from training: its card's held-out pages are the set's, as the training job writes them."""
    preview = client.get("/api/training/set", params={"teacher": TEACHER, "scope_ids": [project["folder"].id],
                                                      "held_out_ids": held_out})
    assert preview.status_code == 200, preview.text
    ts = preview.json()
    out = tmp_path / f"out-{job[:4]}"
    out.mkdir()
    (out / "reader_best.mlmodel").write_bytes(b"trained weights")
    return land_trained_reader(out, job_id=job, model_name="reader", card={
        "teacher": TEACHER, "base": BASE, "training_set": ts, "held_out": ts["held_out"]})


def _run(client, db, **body):
    r = client.post("/api/evaluation/runs", json={"checked": CHECKED, **body})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    assert kind == "evaluate-models"
    evaluation.register_job_kinds()
    jobs.KINDS[kind].run(db, subject)
    status = client.get(f"/api/evaluation/runs/{job_id}")
    assert status.status_code == 200, status.text
    return job_id, status.json()


@pytest.fixture
def readers(monkeypatch, tmp_path):
    fake = Readers(trained_path="")
    monkeypatch.setattr(kraken_runtime, "read_given_lines", fake)
    return fake


def test_held_out_pages_are_never_in_the_training_set(client, project):
    """distill.eval.held-out-checked-pages: scores come "never from a page any candidate trained on".
    WHY: the held-out pages carry the teacher's pass too; only the request's hold-out keeps them out of the
    set. A held-out page that taught the reader would make its score on that page meaningless."""
    scope = {"teacher": TEACHER, "scope_ids": [project["folder"].id]}
    everything = client.get("/api/training/set", params=scope).json()
    held_ids = [d.id for d in project["held"]]
    kept_back = client.get("/api/training/set", params={**scope, "held_out_ids": held_ids}).json()

    assert everything["pages"] == 3 and everything["held_out"] == []
    assert kept_back["pages"] == 1
    assert {h["document_id"] for h in kept_back["held_out"]} == set(held_ids)
    assert kept_back["lines"] == everything["lines"] // 3


def test_each_candidate_is_scored_on_exactly_the_held_out_pages_with_the_one_cer(client, db, tmp_path, project,
                                                                                 readers, monkeypatch):
    """distill.eval.job, distill.eval.candidates-out-of-the-box, distill.eval.cer-variants.
    WHY: a bake-off is only fair when every model reads the same pages, none of which it trained on, and
    is scored by the one CER (its definition and every named policy), not a second one that drifts. The
    trained reader's base is the out-of-the-box reader on this Mac; one not downloaded is named, not
    fetched."""
    base_path = _base_installed(tmp_path)
    trained = _trained(client, tmp_path, project, held_out=[d.id for d in project["held"]])
    readers.trained_path = kraken_runtime.recognition_model_path(trained)
    policies_scored = []
    real = transcription_accuracy.character_error_rate

    def one_cer(reference, hypothesis, *, policy=None):
        policies_scored.append(policy)
        return real(reference, hypothesis, policy=policy)

    monkeypatch.setattr(transcription_accuracy, "character_error_rate", one_cer)

    job_id, status = _run(client, db, candidates=[{"model": trained}])

    plan = status["plan"]
    assert [c["model"] for c in plan["candidates"]] == [trained, BASE]
    assert {"model": "kraken-catmus-medieval", "reader": "kraken",
            "why": "not on this Mac: download it to score it"} in plan["not_on_this_mac"]
    held_photos = sorted(d.path for d in project["held"])
    assert sorted(readers.read[readers.trained_path]) == held_photos
    assert sorted(readers.read[base_path]) == held_photos
    assert project["taught"].path not in sum(readers.read.values(), [])

    result = status["result"]
    by_model = {m["model"]: m for m in result["models"]}
    assert by_model[trained]["role"] == "trained" and by_model[BASE]["role"] == "out of the box"
    assert set(policies_scored) == set(transcription_accuracy.POLICIES)
    assert len(policies_scored) == 2 * 2 * len(transcription_accuracy.POLICIES)  # 2 models x 2 pages
    for policy in transcription_accuracy.POLICIES:
        assert by_model[trained]["scores"][policy]["cer"] == 0.0
        assert by_model[BASE]["scores"][policy]["cer"] > 0.0
        assert by_model[BASE]["scores"][policy]["pages"] == 2
    assert {p["document_id"] for p in by_model[BASE]["per_page"]} == {d.id for d in project["held"]}
    assert result["best"] == trained and result["definition"] == transcription_accuracy.CER_DEFINITION
    assert result["trust"] == {"model": 1, "person": 1}
    assert "best " + trained in status["reason"]


def test_scores_land_on_the_model_and_are_read_back(client, db, tmp_path, project, readers):
    """distill.eval.stored-on-the-model-node: "stored on each model's card ... A later evaluation adds to them
    and never overwrites one."
    WHY: the model node (#5439) reads its scores from the card; a score kept only in the job row is lost
    when finished jobs are cleared, and a re-run that overwrote the first would hide a regression."""
    _base_installed(tmp_path)
    trained = _trained(client, tmp_path, project, held_out=[d.id for d in project["held"]])
    readers.trained_path = kraken_runtime.recognition_model_path(trained)

    first, status = _run(client, db, candidates=[{"model": trained}])
    second, _ = _run(client, db, candidates=[{"model": trained}], add_out_of_the_box=False)

    read = client.get("/api/evaluation/scores", params={"model": trained, "reader": "kraken"})
    assert read.status_code == 200, read.text
    kept = read.json()["evaluations"]
    assert [e["job_id"] for e in kept] == [first, second]
    by_model = {m["model"]: m for m in status["result"]["models"]}
    assert kept[0]["scores"] == by_model[trained]["scores"] and kept[0]["compared_with"] == [BASE]
    assert set(kept[0]["pages"]) == {d.id for d in project["held"]}
    assert kept[0]["checked"] == CHECKED and kept[0]["trust"] == {"model": 1, "person": 1}
    base = client.get("/api/evaluation/scores", params={"model": BASE}).json()["evaluations"]
    assert [e["job_id"] for e in base] == [first]
    # The card is still the reader's: it resolves and keeps its training card.
    assert kraken_runtime.trained_reader_card(trained)["teacher"] == TEACHER
    assert str(tmp_path) not in json.dumps(status["result"])  # no path from this Mac in the answer


def test_a_model_with_no_held_out_pages_is_refused_in_words(client, db, tmp_path, project, readers):
    """distill.eval.held-out-checked-pages.
    WHY: a reader trained with nothing kept back may have learnt every checked page; any score on them
    would flatter it. The refusal must say why in words, before anything is queued."""
    trained = _trained(client, tmp_path, project, held_out=[])
    r = client.post("/api/evaluation/runs", json={"checked": CHECKED, "candidates": [{"model": trained}]})
    assert r.status_code == 422
    assert f"{trained} has no held-out pages" in r.json()["detail"]

    kept = _trained(client, tmp_path, project, held_out=[project["held"][0].id], job="1a2b3c4d-1111-2222-3333-444455556666")
    named = client.post("/api/evaluation/runs", json={"checked": CHECKED, "candidates": [{"model": kept}],
                                                      "held_out_ids": [d.id for d in project["held"]]})
    assert named.status_code == 422 and f"not held out from {kept}" in named.json()["detail"]

    remote = client.post("/api/evaluation/runs", json={"checked": CHECKED, "held_out_ids": [project["held"][0].id],
                                                       "candidates": [{"model": "qwen/qwen3-vl-4b", "reader": "vision",
                                                                       "provider": "openrouter"}]})
    assert remote.status_code == 422 and "remote model target is not built yet" in remote.json()["detail"]
    assert db.execute_fetchone("SELECT COUNT(*) FROM jobs WHERE kind = 'evaluate-models'")[0] == 0
