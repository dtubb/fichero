"""`source.check.*` (docs/contributor_manual/specs/source/checking.md): checking a layer's proposals, tested to the spec.

Each test is named after the behaviour it proves and quotes it. Everything goes through the public
surface: the check routes (`/api/check/...`), the readings route, the training route; the job is run as
the scheduler runs it (`jobs.KINDS["check"].run`). The checker models are stubs at the model boundary
(`llm.vision`, `llm.chat`): the real checker (Fable) waits for credit.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import fichero_server.llm as llm
from fichero_server.execution import jobs
from fichero_server.models import ActionAudit, DocType, Document
from fichero_server.models.knowledge import ClaimCurationState, KnowledgeClaim, KnowledgeEntity
from tests.unit.training.test_kraken_training_set import _page

CHECKER = "anthropic/claude-fable"
SIZE = (274, 396)


class Checker:
    """A checker model stand-in: the n-th proposal it is shown gets the n-th scripted verdict (then
    confirm). It records what it was shown."""

    def __init__(self, script=()):
        self.script = list(script)
        self.shown: list[dict] = []

    def answer(self, prompt, images):
        self.shown.append({"prompt": prompt, "images": len(images)})
        verdict = self.script.pop(0) if self.script else {"verdict": "confirm", "why": "it reads so"}
        return "<think>I looked at the stroke.</think>" + json.dumps(verdict, ensure_ascii=False)


@pytest.fixture(autouse=True)
def checker(monkeypatch):
    stub = Checker()

    async def vision(images, prompt, config, **kw):
        return stub.answer(prompt, images)

    async def chat(prompt, config, **kw):
        return stub.answer(prompt if isinstance(prompt, str) else json.dumps(prompt), [])

    monkeypatch.setattr(llm, "vision", vision)
    monkeypatch.setattr(llm, "chat", chat)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)  # the test runs the job itself
    return stub


@pytest.fixture
def page(db, tmp_path):
    folder = Document(name="SM_NPQ_C01", doc_type=DocType.folder)
    db.save(folder)
    doc = _page(db, tmp_path, "SM_NPQ_C01_001", folder, read_by="google/gemini-3-flash-preview", size=SIZE)
    doc.metadata = {**(doc.metadata or {}), "width": SIZE[0], "height": SIZE[1]}
    db.save(doc)
    return folder, doc


@pytest.fixture
def statements(db, page):
    folder, doc = page
    juan = KnowledgeEntity(canonical_name="Juan de Mosquera", entity_type="person", aliases=["J. Mosquera"],
                           source_document_ids=[doc.id])
    db.save(juan)
    made = []
    for i, (s, v, o) in enumerate([("Juan de Mosquera", "sold", "a house"), ("Juan de Mosquera", "owed", "ten pesos"),
                                   ("the notary", "witnessed", "the sale")]):
        claim = KnowledgeClaim(text=f"{s} {v} {o}.", svo_subject=s, svo_verb=v, svo_object=o,
                               source_document_id=doc.id, source_excerpt=f"excerpt {i}: {s} {v} {o}",
                               entity_ids=[juan.id])
        db.save(claim)
        made.append(claim)
    return folder, made, juan


def _run(client, db, **body):
    r = client.post("/api/check/runs", json={"provider": "openrouter", "model": CHECKER, **body})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    subject = db.execute_fetchone("SELECT subject FROM jobs WHERE id = ?", [job_id])[0]
    from fichero_server.checking import job as check_job

    check_job.register_job_kinds()
    try:
        jobs.KINDS["check"].run(db, subject)
    except jobs.JobCancelled:
        pass
    return job_id


def _verdicts(client, **query):
    r = client.get("/api/check/verdicts", params=query)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _lines(client, db, doc):
    from fichero_server.models import Segment

    rows = [s for s in db.query(Segment, document_id=doc.id) if s.kind == "line" and not s.deleted_at]
    return {s.id: client.get(f"/api/segments/{s.id}/readings").json()["items"] for s in rows}


def test_source_check_verdict_recorded(client, db, page, checker):
    """source.check.verdict-recorded: "each verdict on a proposal is one record of the layer, the proposal,
    the verdict (confirm, correct or reject), the checker's reasons, the checker, its trust level, the run
    and the episode, written through the audited action `check.verdict`; the proposal itself is not edited.\""""
    folder, doc = page
    before = _lines(client, db, doc)
    job_id = _run(client, db, layer="readings", scope_ids=[folder.id])
    verdicts = _verdicts(client, run_id=job_id)

    readings = {r["id"]: r for items in before.values() for r in items}
    assert len(verdicts) == len(before) > 0
    assert {v["target_id"] for v in verdicts} <= set(readings)
    for v in verdicts:
        assert v["layer"] == "readings" and v["verdict"] in ("confirm", "correct", "reject")
        assert v["reasons"] and v["checker"] == CHECKER and v["trust"] == "model"
        assert v["run_id"] == job_id and v["episode_id"]
    after = {r["id"]: r for items in _lines(client, db, doc).values() for r in items}
    assert all(after[i]["content"] == r["content"] for i, r in readings.items()), "a check never edits"
    audit = len(db.query(ActionAudit, action_name="check.verdict"))
    assert audit == len(verdicts)


def test_source_check_model_never_a_person(client, db, page, checker):
    """source.check.model-never-a-person: "a verdict made by a model, or written through a run or by an
    agent, is recorded at the trust level `model`; only a person's own verdict is `person`; a caller cannot
    set it. A reading a model's correction writes is a machine's reading, never a person's.\""""
    folder, doc = page
    checker.script = [{"verdict": "correct", "why": "the d is looped", "correction": {"text": "Yten dixo"}}]
    job_id = _run(client, db, layer="readings", scope_ids=[folder.id])
    corrected = next(v for v in _verdicts(client, run_id=job_id) if v["verdict"] == "correct")
    assert corrected["trust"] == "model"
    new = next(r for items in _lines(client, db, doc).values() for r in items if r["id"] == corrected["replacement_id"])
    assert new["provenance_kind"] != "human" and new["content"] == "Yten dixo"

    person = client.post("/api/check/verdicts", json={"layer": "readings", "target_id": corrected["target_id"],
                                                      "verdict": "confirm", "reasons": "I read it so"})
    assert person.status_code == 200 and person.json()["trust"] == "person"
    agent = client.post("/api/mcp/tools/check/verdicts", json={"layer": "readings", "target_id": corrected["target_id"],
                                                               "verdict": "confirm", "reasons": "an agent read it so"})
    assert agent.status_code == 200 and agent.json()["trust"] == "model", "an agent is not a person"
    forged = client.post("/api/check/verdicts", json={"layer": "readings", "target_id": corrected["target_id"],
                                                      "verdict": "confirm", "reasons": "x", "trust": "person"})
    assert forged.status_code == 422, "the trust level is the server's to set"


def test_source_check_correction_names_the_first(client, db, page, statements, checker):
    """source.check.correction-names-the-first: "a correction names the proposal it replaces: for a reading,
    a new reading of the same line with `corrects_representation_id` set to the reading checked, the first
    left as it was; for a statement or an entity, the corrected values held on the verdict, naming the
    statement or entity they would replace.\""""
    folder, doc = page
    checker.script = [{"verdict": "correct", "why": "an abbreviation", "correction": {"text": "que dixo"}}]
    job_id = _run(client, db, layer="readings", scope_ids=[folder.id])
    v = next(v for v in _verdicts(client, run_id=job_id) if v["verdict"] == "correct")
    line = next(items for items in _lines(client, db, doc).values() if any(r["id"] == v["target_id"] for r in items))
    first = next(r for r in line if r["id"] == v["target_id"])
    new = next(r for r in line if r["id"] == v["replacement_id"])
    assert new["corrects_representation_id"] == first["id"] and first["content"] != "que dixo"

    _f, claims, _juan = statements
    checker.script = [{"verdict": "correct", "why": "he bought it", "correction": {
        "text": "Juan de Mosquera bought a house.", "subject": "Juan de Mosquera", "relation": "bought",
        "object": "a house"}}]
    run = _run(client, db, layer="claims", scope_ids=[folder.id])
    v = next(v for v in _verdicts(client, run_id=run) if v["verdict"] == "correct")
    assert v["target_id"] == claims[0].id and v["correction"]["relation"] == "bought"
    assert db.get(KnowledgeClaim, claims[0].id).text == "Juan de Mosquera sold a house.", "never rewritten by a model"


def test_source_check_curation_is_a_persons(client, db, page, statements, checker):
    """source.check.curation-is-a-persons: "a model's verdict never moves a statement to `curated` or
    `rejected`, nor an entity to `verified` or `rejected`; a model's *reject* moves an `unreviewed` statement
    to `shortlisted`, for a person to look at, and nothing further.\""""
    folder, claims, juan = statements
    curated = claims[2]
    curated.curation_state = ClaimCurationState.curated
    db.save(curated)
    checker.script = [{"verdict": "reject", "why": "not in the text"}, {"verdict": "confirm", "why": "so it says"},
                      {"verdict": "reject", "why": "a person curated it, but still"}]
    _run(client, db, layer="claims", scope_ids=[folder.id])
    states = [db.get(KnowledgeClaim, c.id).curation_state.value for c in claims]
    assert states == ["shortlisted", "unreviewed", "curated"]

    checker.script = [{"verdict": "reject", "why": "no such person"}]
    _run(client, db, layer="entities", scope_ids=[folder.id])
    assert db.get(KnowledgeEntity, juan.id).curation_state.value == "unreviewed"


def test_source_check_traces_in_the_ledger(client, db, page, checker):
    """source.check.traces-in-the-ledger: "each call of a checker model is one episode in the ledger with
    its prompt, raw answer and thinking, and each verdict names its episode.\""""
    folder, _doc = page
    job_id = _run(client, db, layer="readings", scope_ids=[folder.id])
    ledger = {}
    for path in (Path(db.path).parent / "episodes").glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            ledger[record["episode_id"]] = record
    verdicts = _verdicts(client, run_id=job_id)
    assert len({v["episode_id"] for v in verdicts}) == len(verdicts) == len(checker.shown)
    for v in verdicts:
        episode = ledger[v["episode_id"]]
        assert episode["exchange"]["prompt"] and episode["exchange"]["output"]
        assert episode["exchange"]["thinking"] == "I looked at the stroke."


def test_source_check_readings_card(client, db, page, checker, tmp_path, monkeypatch):
    """source.check.readings-card: "the palaeographer reviewer is shown each line's picture and the
    reading that counts for it, and its review of the line is kept as the `review` arm's lesson.\""""
    folder, doc = page
    checker.script = [{"verdict": "correct", "why": "a long s", "correction": {"text": "dixo"}}]
    job_id = _run(client, db, layer="readings", scope_ids=[folder.id])
    counting = {r["content"] for items in _lines(client, db, doc).values() for r in items
                if r["provenance_kind"] != "workflow"}
    assert all(shown["images"] == 1 for shown in checker.shown)
    assert all(any(json.dumps(text, ensure_ascii=False) in shown["prompt"] for text in counting)
               for shown in checker.shown)
    assert _verdicts(client, run_id=job_id)

    # The review arm finds the run's verdicts: through the training job, with Hugging Face replaced.
    from fichero_server.training import job as training_job
    from fichero_server.training.job import TrainVisionLoraRequest
    from tests.unit.training.test_training_job import FakeHub

    monkeypatch.setattr(training_job, "_work_dir", lambda job_id: tmp_path / "work" / job_id)
    hub = FakeHub(stages=("failed",), message="stopped for the test")
    started = training_job.start(db, TrainVisionLoraRequest(scope_ids=[folder.id],
                                                            teacher="google/gemini-3-flash-preview", arm="review",
                                                            pages_may_leave=True), started_by="owner",
                                 target_factory=lambda: hub)
    subject = db.execute_fetchone("SELECT subject FROM jobs WHERE id = ?", [started["job_id"]])[0]
    with pytest.raises(Exception, match="stopped for the test"):
        training_job.run(db, subject, target=hub, sleep=lambda s: None)
    trained = client.get(f"/api/training/jobs/{started['job_id']}").json()
    assert trained["training_set"]["arms"]["review"] >= 1


def test_source_check_claims_card(client, db, statements, checker):
    """source.check.claims-card: "a statements checker is shown each statement's text, subject, relation
    and object, and the excerpt it came from.\""""
    folder, claims, _juan = statements
    _run(client, db, layer="claims", scope_ids=[folder.id])
    assert len(checker.shown) == len(claims)
    for shown, claim in zip(checker.shown, claims):
        for part in (claim.text, claim.svo_subject, claim.svo_verb, claim.svo_object, claim.source_excerpt):
            assert part in shown["prompt"]


def test_source_check_entities_card(client, db, statements, checker):
    """source.check.entities-card: "an entities checker is shown each entity's name, type and other names,
    and the excerpts that mention it.\""""
    folder, claims, juan = statements
    _run(client, db, layer="entities", scope_ids=[folder.id])
    (shown,) = checker.shown
    for part in ("Juan de Mosquera", "person", "J. Mosquera", claims[0].source_excerpt):
        assert part in shown["prompt"]


def test_source_check_run_is_a_job(client, db, page, checker):
    """source.check.run-is-a-job: "a check run is one job in Activity over a scope, from the API, the CLI
    and MCP, with its counts in words (confirmed, corrected, rejected, unanswered), and can be stopped;
    what was checked stays.\""""
    folder, _doc = page
    checker.script = [{"verdict": "reject", "why": "a ruler, not writing"}, "not json at all"]
    job_id = _run(client, db, layer="readings", scope_ids=[folder.id])
    status = client.get(f"/api/check/runs/{job_id}").json()
    assert status["counts"]["reject"] == 1 and status["counts"]["unanswered"] == 1
    assert "rejected" in status["reason"] and "unanswered" in status["reason"]
    assert jobs.KINDS["check"].lane == "remote"

    r = client.post("/api/check/runs", json={"provider": "openrouter", "model": CHECKER, "layer": "readings",
                                             "scope_ids": [folder.id]})
    stopped = r.json()["job_id"]
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [stopped])
    assert client.post(f"/api/check/runs/{stopped}/cancel").status_code == 200
    shown = len(checker.shown)
    subject = db.execute_fetchone("SELECT subject FROM jobs WHERE id = ?", [stopped])[0]
    with pytest.raises(jobs.JobCancelled):
        jobs.KINDS["check"].run(db, subject)
    assert len(checker.shown) == shown and _verdicts(client, run_id=job_id), "what was checked stays"
    assert client.get("/api/check/runs/nope").status_code == 404


def test_source_check_person_checks_the_same_way(client, db, statements):
    """source.check.person-checks-the-same-way: "a person's verdict goes through the same action and is
    recorded at `person`; a person's *reject* of a statement is still taken through the statement's own
    curation, never by the verdict.\""""
    _folder, claims, _juan = statements
    r = client.post("/api/check/verdicts", json={"layer": "claims", "target_id": claims[1].id, "verdict": "reject",
                                                 "reasons": "he never owed it"})
    assert r.status_code == 200 and r.json()["trust"] == "person" and r.json()["checker"]
    assert db.get(KnowledgeClaim, claims[1].id).curation_state.value == "unreviewed"
    audit = len(db.query(ActionAudit, action_name="check.verdict"))
    assert audit == 1
