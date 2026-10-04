"""`distill.reasoning.*` and `distill.set.keeps-reasons` (docs/contributor_manual/specs/compute/distillation.md), tested to the spec.

Each test is named after the behaviour it proves and quotes it. Everything goes through the public surface:
`POST /api/training/reasons`, `POST /api/training/vision-lora`, `POST /api/training/reasons-ab` and their
status routes; each job is run as the scheduler runs it (`jobs.KINDS[kind].run`). The models are stubs at
the model boundary (`llm.vision`), and Hugging Face is a fake that records what was sent: the real teacher
and the real training wait for credit.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PIL import Image

import fichero_server.llm as llm
from fichero_server.execution import jobs
from fichero_server.models import DocType, Document
from tests.unit.training.test_kraken_training_set import _page
from tests.unit.training.test_training_job import FakeHub

CHECKED = "fable-checked"  # the checked pass's model id: the right readings
TEACHER = "Qwen/Qwen3-VL-8B-Thinking"
SIZE = (274, 396)


class Models:
    """Stand-ins at `llm.vision`. They know each line picture's checked text (`truth`). The teacher reads
    every line right, except the lines in `teacher_wrong`; the students answer as `students` says."""

    def __init__(self):
        self.truth: dict[str, str] = {}
        self.teacher_wrong: set[str] = set()
        self.teacher_near: set[str] = set()  # one letter off: within the set CER, so its reasons are kept
        self.students: dict[str, str] = {}  # model -> "right" | "one-off"
        self.calls: list[tuple[str, str]] = []

    async def vision(self, images, prompt, config, **kw):
        self.calls.append((config.model, prompt))
        text = self.truth[images[0]]
        if "Read each as a palaeographer" in prompt and config.model == TEACHER:
            read = "something else entirely" if text in self.teacher_wrong else text
            if text in self.teacher_near:
                read = text[:-1] + ("y" if text[-1] != "y" else "z")
            return ("the second letter is a long s</think>" + json.dumps(
                [{"letterforms": "long s", "abbreviations": [{"as_written": "q̃", "expanded": "que"}],
                  "uncertain": [], "text": read}], ensure_ascii=False))
        read = text if self.students.get(config.model, "right") == "right" else text + "x"
        if "Read each as a palaeographer" in prompt:
            return json.dumps([{"letterforms": "", "abbreviations": [], "uncertain": [], "text": read}])
        return json.dumps([read])


@pytest.fixture
def models(monkeypatch):
    stub = Models()
    monkeypatch.setattr(llm, "vision", stub.vision)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)  # the test runs each job itself
    return stub


@pytest.fixture
def project(db, tmp_path, models):
    """Two pages whose lines a person checked; the second is held out. Each photograph is noise, so every
    line picture differs and the stand-ins can tell them apart."""
    from fichero_server.training.reasons import checked_lines
    from fichero_server.llm.line_reader import _crop_data_uri

    folder = Document(name="SM_NPQ_C01", doc_type=DocType.folder)
    db.save(folder)
    pages = []
    for name in ("SM_NPQ_C01_001", "SM_NPQ_C01_002"):
        page = _page(db, tmp_path, name, folder, read_by=CHECKED, size=SIZE)
        page.metadata = {**(page.metadata or {}), "width": SIZE[0], "height": SIZE[1]}
        db.save(page)
        Image.frombytes("RGB", SIZE, os.urandom(SIZE[0] * SIZE[1] * 3)).save(page.path, format="PNG")
        pages.append(page)
    lines, photos, _ = checked_lines(db, scope_ids=[folder.id], checked=CHECKED)
    images = {doc_id: Image.open(path) for doc_id, path in photos.items()}
    models.truth = {_crop_data_uri(images[line.document_id], line.polygon): line.checked for line in lines}
    return folder, pages[0], pages[1], lines


def _run(db, kind, job_id):
    from fichero_server.checking import job as check_job
    from fichero_server.training import job as training_job, reasons_job

    for module in (reasons_job, training_job, check_job):
        module.register_job_kinds()
    subject = db.execute_fetchone("SELECT subject FROM jobs WHERE id = ?", [job_id])[0]
    return jobs.KINDS[kind].run(db, subject)


def _gather(client, db, folder, held_out):
    r = client.post("/api/training/reasons", json={"scope_ids": [folder.id], "checked": CHECKED, "provider": "omlx",
                                                   "model": TEACHER, "held_out_ids": [held_out.id],
                                                   "prompt_file": None})
    assert r.status_code == 200, r.text
    _run(db, "gather-reasons", r.json()["job_id"])
    return r.json()["job_id"]


def _ledger(db):
    return [json.loads(line) for path in sorted((Path(db.path).parent / "episodes").glob("*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()]


def _train(client, db, folder, held_out, tmp_path, monkeypatch, arm):
    """Start the vision card through its route; Hugging Face is a fake that stops the Job once it has seen
    what was sent. Returns the job's status, what was submitted, and the pairs that were sent."""
    from fichero_server.training import hf_jobs
    from fichero_server.training import job as training_job

    hub = FakeHub(stages=("failed",), message="stopped once the set was sent")
    monkeypatch.setattr(hf_jobs, "HfJobsTarget", lambda *a, **k: hub)
    monkeypatch.setattr(training_job, "_work_dir", lambda job_id: tmp_path / "work" / job_id)
    r = client.post("/api/training/vision-lora", json={"scope_ids": [folder.id], "teacher": CHECKED,
                                                       "held_out_ids": [held_out.id], "arm": arm,
                                                       "pages_may_leave": True, "flavor": "l4x1"})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    with pytest.raises(Exception, match="stopped once the set was sent"):
        _run(db, "train-a-model", job_id)
    pairs = [json.loads(line) for line in
             (tmp_path / "work" / job_id / "data" / "pairs.jsonl").read_text(encoding="utf-8").splitlines()]
    return client.get(f"/api/training/jobs/{job_id}").json(), hub.submitted[0], pairs


def test_distill_reasoning_gather_is_a_job(client, db, project, models):
    """distill.reasoning.gather-is-a-job: "asking a palaeographer for its reasons on a scope's checked lines
    is one job in Activity, from the API, the CLI and MCP, with its counts in words (lines asked about, with
    reasons, with thinking, unanswered), held-out pages never asked about, and can be stopped before the
    next line; what was gathered stays.\""""
    folder, kept, held_out, lines = project
    job_id = _gather(client, db, folder, held_out)
    status = client.get(f"/api/training/reasons/{job_id}").json()
    asked = sum(1 for line in lines if line.document_id == kept.id)
    assert status["result"]["lines"] == status["result"]["reasoned"] == status["result"]["with_thinking"] == asked
    assert f"{asked} of {asked} lines have reasons" in status["reason"]
    held_texts = {line.checked for line in lines if line.document_id == held_out.id} - {
        line.checked for line in lines if line.document_id == kept.id}
    assert not any(text in models.truth.values() and text in p for _m, p in models.calls for text in held_texts)
    assert jobs.KINDS["gather-reasons"].lane == "remote"

    r = client.post("/api/training/reasons", json={"scope_ids": [folder.id], "checked": CHECKED, "provider": "omlx",
                                                   "model": TEACHER, "held_out_ids": [held_out.id]})
    stopped = r.json()["job_id"]
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [stopped])
    assert client.post(f"/api/training/reasons/{stopped}/cancel").status_code == 200
    calls = len(models.calls)
    with pytest.raises(jobs.JobCancelled):
        _run(db, "gather-reasons", stopped)
    assert len(models.calls) == calls and len(_ledger(db)) == asked, "what was gathered stays"
    assert client.post("/api/training/reasons", json={"scope_ids": [], "checked": "c", "provider": "omlx",
                                                      "model": "m"}).status_code == 422
    assert client.get("/api/training/reasons/nope").status_code == 404


def test_distill_reasoning_traces_in_the_ledger(client, db, project, models):
    """distill.reasoning.traces-in-the-ledger: "a reasoning teacher's traces for each line (letterforms,
    abbreviations and expansions, uncertain readings with alternatives, then the transcription) are kept in
    the episode ledger with the teacher's card, prompt file, run, time and cost, and its readings name their
    episode; no second store holds traces." Built and pinned here: the trace, the teacher, the prompt file,
    the time, by line. NOT built (PARTIAL in the spec): the call's cost, and the teacher's readings landing as
    a pass that names its episodes."""
    folder, kept, held_out, lines = project
    prompt = Path(db.path).parent / "palaeographer.txt"
    from fichero_server.training.reasons import READ_PROMPT

    prompt.write_text("Recipe prompt. " + READ_PROMPT, encoding="utf-8")
    r = client.post("/api/training/reasons", json={"scope_ids": [folder.id], "checked": CHECKED, "provider": "omlx",
                                                   "model": TEACHER, "held_out_ids": [held_out.id],
                                                   "prompt_file": str(prompt)})
    _run(db, "gather-reasons", r.json()["job_id"])
    episodes = _ledger(db)
    kept_lines = {line.line_id for line in lines if line.document_id == kept.id}
    assert {item["line_id"] for e in episodes for item in e["lines"]} == kept_lines
    for episode in episodes:
        assert episode["model"]["model"] == TEACHER and episode["model"]["prompt_file"] == "palaeographer.txt"
        assert episode["exchange"]["prompt"].startswith("Recipe prompt.") and episode["timing"]["seconds"] >= 0
        (item,) = episode["lines"]
        assert item["letterforms"] == "long s" and item["abbreviations"][0]["expanded"] == "que"
        assert item["thinking"] == "the second letter is a long s"


def test_distill_set_keeps_reasons(client, db, project, models, tmp_path, monkeypatch):
    """distill.set.keeps-reasons: "where the teacher gave its reasons, the set keeps them, and a student can
    be trained to give them.\""""
    folder, _kept, held_out, _lines = project
    _gather(client, db, folder, held_out)
    status, submitted, pairs = _train(client, db, folder, held_out, tmp_path, monkeypatch, arm="why")
    assert status["training_set"]["arms"]["why"] == len(pairs) > 0
    args = submitted["script_args"]
    assert args[args.index("--arm") + 1] == "why"
    for pair in pairs:
        (reasoned,) = json.loads(pair["arms"]["why"]["answer"])
        assert reasoned["letterforms"] == "long s" and reasoned["abbreviations"][0]["expanded"] == "que"
        assert pair["arms"]["thinking"]["answer"].startswith("<think>\nthe second letter is a long s\n</think>")


def test_distill_reasoning_answer_is_checked(client, db, project, models, tmp_path, monkeypatch):
    """distill.reasoning.answer-is-checked: "in a reasoning set the answer is always the person's checked
    transcription; a trace is kept only where the teacher's own reading is within the set CER of it, and the
    count dropped is stated on the set.\""""
    folder, kept, held_out, lines = project
    kept_lines = [line for line in lines if line.document_id == kept.id]
    wrong = kept_lines[0]
    near = next(line for line in kept_lines[1:] if len(line.checked) >= 20)
    models.teacher_wrong, models.teacher_near = {wrong.checked}, {near.checked}
    _gather(client, db, folder, held_out)
    status, _submitted, pairs = _train(client, db, folder, held_out, tmp_path, monkeypatch, arm="why")
    by_id = {p["line_id"]: p for p in pairs}
    assert "why" not in by_id[wrong.line_id]["arms"] and "thinking" not in by_id[wrong.line_id]["arms"]
    assert "why" in by_id[near.line_id]["arms"], "a reading within the set CER keeps its reasons"
    assert status["training_set"]["arms_dropped_outside_cer"]["why"] == 1
    checked = {line.line_id: line.checked for line in lines}
    for pair in pairs:
        for arm, lesson in pair["arms"].items():
            answer = lesson["answer"].split("</think>")[-1].strip()
            (said,) = json.loads(answer)
            assert (said["text"] if isinstance(said, dict) else said) == checked[pair["line_id"]], arm


def test_distill_reasoning_two_arms(client, db, project, models, tmp_path, monkeypatch):
    """distill.reasoning.two-arms: "the same base, lines, split and settings train an answer-only student and a
    reasoning-and-answer student, so the A/B measures the reasons alone.\""""
    from fichero_server.training import hf_vision_lora_train as trainer  # the script the Job runs

    folder, kept, held_out, lines = project
    models.teacher_wrong = {next(line for line in lines if line.document_id == kept.id).checked}
    _gather(client, db, folder, held_out)
    _s, answer_job, pairs = _train(client, db, folder, held_out, tmp_path, monkeypatch, arm="answer")
    _s, why_job, why_pairs = _train(client, db, folder, held_out, tmp_path, monkeypatch, arm="why")
    a, w = answer_job["script_args"], why_job["script_args"]
    strip = lambda args: [x for i, x in enumerate(args) if x not in ("answer", "why") and "/" not in x]  # noqa: E731
    assert strip(a) == strip(w) and a[a.index("--base") + 1] == w[w.index("--base") + 1]
    assert [p["line_id"] for p in pairs] == [p["line_id"] for p in why_pairs]
    answer_lines = {p["line_id"] for p in trainer.select(pairs, "answer")}
    why_lines = {p["line_id"] for p in trainer.select(why_pairs, "why")}
    assert answer_lines == why_lines and len(answer_lines) == len(pairs) - 1, "the dropped line leaves both arms"


def test_distill_reasoning_ab_decides(client, db, project, models, tmp_path, monkeypatch):
    """distill.reasoning.ab-decides: "both students, the teacher and the cheap baseline are measured on
    held-out checked pages (one CER, WER, speed and peak memory on a 16 GB Mac, with and without reasoning at
    run time, trace and training cost); the reasoning student is adopted only if it beats the answer-only one
    beyond the noise band, and both cards record the result." Built and pinned: CER, WER, speed, reasoning on
    and off, the noise band, both cards. NOT built (PARTIAL): peak memory, and the trace and training cost."""
    from fichero_server.llm import mlx_model_store as store_module
    from fichero_server.llm.mlx_model_store import TRAINED_CARD, MLXModelStore

    store = MLXModelStore(root=tmp_path / "mlx")
    monkeypatch.setattr(store_module, "get_mlx_model_store", lambda: store)
    for name in ("answer-only", "with-why"):
        store.trained_dir(f"fichero-trained/{name}").mkdir(parents=True)
        (store.trained_dir(f"fichero-trained/{name}") / TRAINED_CARD).write_text("{}")
    folder, _kept, held_out, lines = project
    models.students = {"fichero-trained/answer-only": "one-off", "fichero-trained/with-why": "right"}
    contenders = [{"label": "answer-only", "provider": "omlx", "model": "fichero-trained/answer-only"},
                  {"label": "with-why", "provider": "omlx", "model": "fichero-trained/with-why", "arm": "why"},
                  {"label": "teacher", "provider": "omlx", "model": TEACHER, "role": "teacher"},
                  {"label": "baseline", "provider": "omlx", "model": "kraken-zenodo", "role": "baseline"}]
    r = client.post("/api/training/reasons-ab", json={"checked": CHECKED, "held_out_ids": [held_out.id],
                                                      "contenders": contenders})
    assert r.status_code == 200, r.text
    _run(db, "reasons-ab", r.json()["job_id"])
    result = client.get(f"/api/training/reasons-ab/{r.json()['job_id']}").json()["result"]
    scores = {s["label"]: s for s in result["scores"]}
    assert scores["with-why"]["cer"] == 0 < scores["answer-only"]["cer"] and scores["answer-only"]["wer"] > 0
    assert scores["with-why (no reasoning)"]["reasoning"] is False and "seconds_per_line" in scores["teacher"]
    held = sum(1 for line in lines if line.document_id == held_out.id)
    assert all(s["lines"] == held for s in scores.values())
    assert result["verdicts"]["with-why"]["adopted"] and result["verdicts"]["with-why"]["against"] == "answer-only"
    for name in ("answer-only", "with-why"):
        card = json.loads((store.trained_dir(f"fichero-trained/{name}") / TRAINED_CARD).read_text())
        assert card["reasons_ab"][0]["verdicts"]["with-why"]["adopted"]

    models.students["fichero-trained/answer-only"] = "right"  # now no gain beyond the noise band
    r = client.post("/api/training/reasons-ab", json={"checked": CHECKED, "held_out_ids": [held_out.id],
                                                      "contenders": contenders})
    _run(db, "reasons-ab", r.json()["job_id"])
    again = client.get(f"/api/training/reasons-ab/{r.json()['job_id']}").json()
    assert not again["result"]["verdicts"]["with-why"]["adopted"] and "No reasoning student" in again["reason"]
    assert client.post("/api/training/reasons-ab", json={"checked": CHECKED, "held_out_ids": [],
                                                         "contenders": contenders}).status_code == 422
