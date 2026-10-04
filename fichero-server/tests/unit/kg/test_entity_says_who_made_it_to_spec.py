"""Every entity says who put it in the knowledge graph (#4869, #4868), tested to the spec
(docs/contributor_manual/specs/kg/kg-tables.md): `kg.entity.says-who-made-it`.

Through the public routes: a names run (the recipe's names card, `2 · Extract Entities`, with a spaCy pin) through
`POST /api/workflow-execution/execute`, a person's entity through `POST /api/entities`, the entity list, and the
`entity.take_back_run` action through `POST /api/actions/invoke`. Stubbed only at the model boundary: spaCy's NER call.
"""
from __future__ import annotations

import time

import pytest

from fichero_server.models import DocType, Document, FileType
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity

PAGE_TEXT = {"p0": "Don Juan de Mosquera vendió a Ysabel de Rojas una casa en Popayán.",
             "p1": "Ysabel de Rojas y Francisco Arboleda fueron a Cali."}
NAMES = {"Juan de Mosquera": "person", "Ysabel de Rojas": "person", "Francisco Arboleda": "person",
         "Popayán": "location", "Cali": "location"}


@pytest.fixture
def spacy_finds_names(monkeypatch):
    """spaCy's NER: every known name that occurs in the text, as spaCy would report it."""
    from fichero_server.knowledge import spacy_ner

    def extract(text, language=None, model=None):
        return [spacy_ner.EntitySpan(text=n, fichero_type=t, start=text.index(n), end=text.index(n) + len(n),
                                     label="PER" if t == "person" else "LOC")
                for n, t in NAMES.items() if n in text]

    monkeypatch.setattr(spacy_ner, "extract_entities", extract)


@pytest.fixture
def pages(db, tmp_path):
    from PIL import Image

    from fichero_server.workflows.default_workflows import seed_default_workflows

    seed_default_workflows(db)
    out = {}
    for name, text in PAGE_TEXT.items():
        Image.new("RGB", (32, 32), "white").save(tmp_path / f"{name}.png")
        doc = Document(name=f"{name}.png", doc_type=DocType.file, file_type=FileType.image,
                       path=str(tmp_path / f"{name}.png"), page_content=text)
        db.save(doc)
        out[name] = doc.id
    return out


def _names_run(client, db, doc_ids, model="es_core_news_sm"):
    from fichero_server.workflows.default_workflows import preset_workflow_id

    r = client.post("/api/workflow-execution/execute", json={
        "workflow_id": preset_workflow_id("2 · Extract Entities"), "inputs": {"selected_doc_ids": doc_ids},
        "provider_override": "spacy", "model_override": model})
    assert r.status_code == 202, r.text
    thread = r.json()["thread_id"]
    end = time.monotonic() + 60
    while time.monotonic() < end:
        r = client.get(f"/api/workflow-execution/threads/{thread}/status")
        status = r.json() if r.status_code == 200 else {"status": None}
        if status["status"] in ("completed", "failed", "cancelled"):
            assert status["status"] == "completed", status
            return thread
        time.sleep(0.1)
    raise AssertionError(f"run {thread} did not finish")


def _entities(client, **params):
    r = client.get("/api/entities", params={"limit": 500, **params})
    assert r.status_code == 200, r.text
    return {e["canonical_name"]: e for e in r.json()["items"]}


def _entries(entity, role):
    return [a for a in entity["attribution_chain"] if a["role"] == role]


def test_kg_entity_says_who_made_it__a_names_run_names_its_model_on_every_entity(client, db, pages, spacy_finds_names):
    """kg.entity.says-who-made-it: "every entity says who put it in the knowledge graph, in its
    `attribution_chain` ...: a model run as an `extractor` entry naming the provider, the model, the run (`run_id`)
    and when (`at`)"."""
    run = _names_run(client, db, [pages["p0"], pages["p1"]])
    made = _entities(client)
    assert set(made) == set(NAMES)
    for name, entity in made.items():
        (entry,) = _entries(entity, "extractor")
        assert (entry["name"], entry["label"], entry["run_id"]) == ("spacy", "es_core_news_sm", run), name
        assert entry["at"], name


def test_kg_entity_says_who_made_it__a_person_is_named_and_a_later_run_only_adds(client, db, pages,
                                                                                  spacy_finds_names):
    """kg.entity.says-who-made-it: "a person as an `editor` entry naming the account and when. The engine writes
    these entries, never a client. They are only ever added: a later run that finds the same entity adds its own
    entry beside the others, and a person's entry stays whatever runs follow."""
    forged = client.post("/api/entities", json={"canonical_name": "Ysabel de Rojas", "entity_type": "person",
                                                "attribution_chain": [{"role": "extractor", "name": "forged"}]})
    assert forged.status_code == 422, "a client never writes an entry"
    r = client.post("/api/entities", json={"canonical_name": "Ysabel de Rojas", "entity_type": "person"})
    assert r.status_code in (200, 201), r.text
    (person,) = _entries(_entities(client)["Ysabel de Rojas"], "editor")
    assert person["name"] and person["at"]
    assert _entries(_entities(client)["Ysabel de Rojas"], "extractor") == []

    first = _names_run(client, db, [pages["p0"]])
    second = _names_run(client, db, [pages["p1"]], model="es_core_news_md")
    ysabel = _entities(client)["Ysabel de Rojas"]
    assert _entries(ysabel, "editor") == [person], "a person's entry stays"
    assert [(e["label"], e["run_id"]) for e in _entries(ysabel, "extractor")] == [("es_core_news_sm", first),
                                                                                 ("es_core_news_md", second)]


def test_kg_entity_says_who_made_it__one_runs_entities_listed_and_taken_back(client, db, pages, spacy_finds_names):
    """kg.entity.says-who-made-it: "One run's entities can be listed by its run (`GET /api/entities?run_id=`), and
    taken back through one audited action (`entity.take_back_run`, a dry run unless asked): it removes the entities
    that run alone made and nothing has touched since (no other run or person named on them, unreviewed, no claim
    naming them ...); every other entity of the run stays, and the answer says how many and why."""
    first = _names_run(client, db, [pages["p0"]])
    second = _names_run(client, db, [pages["p1"]])
    assert set(_entities(client, run_id=first)) == {"Juan de Mosquera", "Ysabel de Rojas", "Popayán"}
    assert set(_entities(client, run_id=second)) == {"Ysabel de Rojas", "Francisco Arboleda", "Cali"}

    popayan = _entities(client)["Popayán"]
    db.save(KnowledgeClaim(text="Casa en Popayán", entity_ids=[popayan["id"]], source_document_id=pages["p0"]))

    dry = client.post("/api/actions/invoke", json={"name": "entity.take_back_run", "params": {"run_id": first}})
    assert dry.status_code == 200, dry.text
    body = dry.json()["result"]
    assert body["dry_run"] is True and body["entity_count"] == 1 and body["kept_count"] == 2, body
    assert set(body["kept_reasons"]) == {"another run or a person also named it", "a claim names it"}, body
    assert len([e for e in db.query(KnowledgeEntity) if not getattr(e, "deleted_at", None)]) == 5, "dry run"

    done = client.post("/api/actions/invoke", json={"name": "entity.take_back_run",
                                                    "params": {"run_id": first, "dry_run": False}})
    assert done.status_code == 200, done.text
    assert set(_entities(client)) == {"Ysabel de Rojas", "Popayán", "Francisco Arboleda", "Cali"}
    assert _entities(client, run_id=first).keys() == {"Ysabel de Rojas", "Popayán"}


def test_kg_entity_says_who_made_it__a_persons_edit_adds_its_entry_and_keeps_the_entity(client, db, pages,
                                                                                         spacy_finds_names):
    """kg.entity.says-who-made-it: "a person as an `editor` entry ... They are only ever added", and take-back
    removes only what the run alone made: an entity a person has since edited stays."""
    run = _names_run(client, db, [pages["p0"]])
    juan = _entities(client)["Juan de Mosquera"]
    r = client.patch(f"/api/entities/{juan['id']}", json={"canonical_name": "Juan de Mosquera", "entity_type": "person",
                                                        "description": "vecino de Popayán"})
    assert r.status_code == 200, r.text
    juan = _entities(client)["Juan de Mosquera"]
    assert [e["run_id"] for e in _entries(juan, "extractor")] == [run], "the run's entry stays"
    client.post("/api/entities", json={"canonical_name": "Someone Else", "entity_type": "person"})
    (account,) = [e["name"] for e in _entries(_entities(client)["Someone Else"], "editor")]
    assert [e["name"] for e in _entries(juan, "editor")] == [account], "the edit names the account that made it"
    body = client.post("/api/actions/invoke", json={"name": "entity.take_back_run", "params": {"run_id": run}}).json()
    assert body["result"]["kept_reasons"] == {"another run or a person also named it": 1}, body
    assert body["result"]["entity_count"] == 2, "Ysabel and Popayán, which the run alone made"


def test_kg_entity_says_who_made_it__taking_back_withdraws_its_review_pairs(client, db, pages, spacy_finds_names):
    """kg.entity.says-who-made-it: "A review pair still waiting on an entity it removes leaves the queue as withdrawn
    by the system, its reason saying which entity and which run; it is never marked rejected, which is a person's
    decision and teaches the matcher. A pair a person already decided keeps its decision."""
    from fichero_server.models.knowledge import EntityMatchCandidate

    first = _names_run(client, db, [pages["p0"]])   # Juan de Mosquera, Ysabel de Rojas, Popayán
    second = _names_run(client, db, [pages["p1"]])  # Ysabel de Rojas, Francisco Arboleda, Cali
    made = _entities(client)
    for survivor, candidate in (("Juan de Mosquera", "Francisco Arboleda"), ("Popayán", "Cali")):
        r = client.post("/api/kg/review/pairs", json={"survivor_entity_id": made[survivor]["id"],
                                                      "candidate_entity_id": made[candidate]["id"]})
        assert r.status_code == 200, r.text
    decided = next(p for p in client.get("/api/kg/review/pairs").json()["items"] if p["candidate_name"] == "Cali")
    assert client.post(f"/api/kg/review/pairs/{decided['id']}/reject").status_code == 200

    r = client.post("/api/actions/invoke", json={"name": "entity.take_back_run",
                                                 "params": {"run_id": second, "dry_run": False}})
    assert r.status_code == 200, r.text
    assert set(_entities(client)) == {"Juan de Mosquera", "Ysabel de Rojas", "Popayán"}
    assert client.get("/api/kg/review/pairs").json()["items"] == [], "the waiting pair left the queue"
    labels = client.get("/api/kg/review/labels").json()["items"]
    assert [(lab["pair_id"], lab["label"]) for lab in labels] == [(decided["id"], "no_match")], "never rejected"
    rows = {c.id: c for c in db.query(EntityMatchCandidate)}
    (withdrawn,) = [c for c in rows.values() if c.id != decided["id"]]
    assert getattr(withdrawn.state, "value", withdrawn.state) == "withdrawn"
    assert withdrawn.decided_by == "system" and "Francisco Arboleda" in withdrawn.reason and second in withdrawn.reason
    assert getattr(rows[decided["id"]].state, "value", None) == "rejected", "a person's decision is kept"
    assert first
