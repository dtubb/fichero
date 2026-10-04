"""A model run never decides that two names are one entity (#5409), tested to the spec
(docs/contributor_manual/specs/kg/kg-tables.md): `kg.entity.models-propose-merges`.

Names runs (the recipe's names card with a spaCy pin) through `POST /api/workflow-execution/execute`, read back
through `GET /api/entities` and the review queue `GET /api/kg/review/pairs`. Stubbed only at the model boundary:
spaCy's NER (each page's names, as given) and the vector model's nearest neighbours.
"""
from __future__ import annotations

import pytest

from tests.unit.kg.test_entity_says_who_made_it_to_spec import _entities, _names_run

from fichero_server.models import DocType, Document, FileType


@pytest.fixture
def ner(monkeypatch):
    """spaCy's NER: the names listed for each page (by its text), as persons."""
    from fichero_server.knowledge import spacy_ner

    def extract(text, language=None, model=None):
        return [spacy_ner.EntitySpan(text=n, fichero_type="person", start=0, end=len(n), label="PER")
                for n in text.split(" | ")]

    monkeypatch.setattr(spacy_ner, "extract_entities", extract)


@pytest.fixture
def vectors(monkeypatch):
    """The vector model's nearest neighbour: a fixed cosine per pair of names, else nothing."""
    from fichero_server.knowledge import entity_vectors

    near: dict[tuple[str, str], float] = {}

    def find_similar(db, canonical_name, entity_type, description=None, top_k=3):
        from fichero_server.models.knowledge import KnowledgeEntity

        hits = [(e.id, near[(canonical_name, e.canonical_name)], e.canonical_name)
                for e in db.query(KnowledgeEntity, entity_type=entity_type)
                if (canonical_name, e.canonical_name) in near]
        return sorted(hits, key=lambda h: -h[1])[:top_k]

    monkeypatch.setattr(entity_vectors, "find_similar", find_similar)
    monkeypatch.setattr(entity_vectors, "index_entity", lambda **kw: None)
    return near


def _pages(db, tmp_path, *texts):
    from PIL import Image

    from fichero_server.workflows.default_workflows import seed_default_workflows

    seed_default_workflows(db)
    ids = []
    for i, text in enumerate(texts):
        Image.new("RGB", (32, 32), "white").save(tmp_path / f"q{i}.png")
        doc = Document(name=f"q{i}.png", doc_type=DocType.file, file_type=FileType.image,
                       path=str(tmp_path / f"q{i}.png"), page_content=text)
        db.save(doc)
        ids.append(doc.id)
    return ids


def _pairs(client):
    return client.get("/api/kg/review/pairs", params={"limit": 500}).json()["items"]


def test_kg_entity_models_propose_merges__a_close_vector_neighbour_is_proposed_not_merged(client, db, tmp_path,
                                                                                        ner, vectors):
    """kg.entity.models-propose-merges: "A name that is only similar to an existing one (`Don Tomas Polo` and `Don
    Joaquin Polo`, ... two names a vector model puts close together) is a new entity, and the pair goes into the
    entity review queue ... with what made them similar (method `embedding_cosine` ...) in its reason"."""
    vectors[("Don Tomas Polo", "Don Joaquin Polo")] = 0.96
    first, second = _pages(db, tmp_path, "Don Joaquin Polo", "Don Tomas Polo")
    _names_run(client, db, [first])
    _names_run(client, db, [second])
    made = _entities(client)
    assert set(made) == {"Don Joaquin Polo", "Don Tomas Polo"}, made.keys()
    assert made["Don Joaquin Polo"]["aliases"] == []
    (pair,) = _pairs(client)
    assert (pair["survivor_name"], pair["candidate_name"], pair["method"]) == (
        "Don Joaquin Polo", "Don Tomas Polo", "embedding_cosine")
    assert "0.96" in pair["reason"], pair["reason"]


def test_kg_entity_models_propose_merges__a_name_that_only_looks_alike_is_proposed_not_merged(client, db, tmp_path,
                                                                                            ner, vectors):
    """kg.entity.models-propose-merges: a name only similar to an existing one is "a new entity, and the pair goes
    into the entity review queue" (method `similar_name` or `embedding_cosine`), never folded in as an alias: the run-on span `francisco
    de paz Jose Dionicio de Villar Por` stays out of `Jose Dionisio de Villar`'s names, and `Chocó department` out
    of `Chocó`'s."""
    vectors[("francisco de paz Jose Dionicio de Villar Por", "Jose Dionisio de Villar")] = 0.93
    pages = _pages(db, tmp_path, "Jose Dionisio de Villar | Chocó",
                   "francisco de paz Jose Dionicio de Villar Por | Chocó department")
    _names_run(client, db, [pages[0]])
    _names_run(client, db, [pages[1]])
    made = _entities(client)
    assert set(made) == {"Jose Dionisio de Villar", "francisco de paz Jose Dionicio de Villar Por", "Chocó",
                         "Chocó department"}, made.keys()
    assert made["Jose Dionisio de Villar"]["aliases"] == [] and made["Chocó"]["aliases"] == []
    pairs = {(p["survivor_name"], p["candidate_name"]): p for p in _pairs(client)}
    assert set(pairs) == {("Jose Dionisio de Villar", "francisco de paz Jose Dionicio de Villar Por"),
                          ("Chocó", "Chocó department")}, set(pairs)
    assert pairs[("Chocó", "Chocó department")]["method"] == "similar_name"
    assert pairs[("Jose Dionisio de Villar", "francisco de paz Jose Dionicio de Villar Por")]["method"] == "embedding_cosine"


def test_kg_entity_models_propose_merges__the_same_name_written_alike_is_added(client, db, tmp_path, ner, vectors):
    """kg.entity.models-propose-merges: "it adds the name to an existing entity of the same type only when the two
    are the same name once case, accents, punctuation and spacing are set aside, or when the name is already one
    of that entity's names"."""
    pages = _pages(db, tmp_path, "Juan de Mosquera | Quibdó", "juan de  Mosquera, | Quibdo")
    _names_run(client, db, [pages[0]])
    _names_run(client, db, [pages[1]])
    made = _entities(client)
    assert set(made) == {"Juan de Mosquera", "Quibdó"}, made.keys()
    assert made["Quibdó"]["aliases"] == ["Quibdo"]
    assert _pairs(client) == []
    _names_run(client, db, [pages[1]])
    assert set(_entities(client)) == {"Juan de Mosquera", "Quibdó"}, "an alias already held matches"


def test_kg_entity_models_propose_merges__a_name_already_held_is_added_to_its_entity(client, db, tmp_path, ner,
                                                                                   vectors):
    """kg.entity.models-propose-merges: "... or when the name is already one of that entity's names": a person's
    entity `Popayán`, also called `Ciudad de Popayán`, takes a run's `Ciudad de Popayan`; no new entity, no pair."""
    r = client.post("/api/entities", json={"canonical_name": "Popayán", "entity_type": "person",
                                           "aliases": ["Ciudad de Popayán"]})
    assert r.status_code in (200, 201), r.text
    (page,) = _pages(db, tmp_path, "Ciudad de Popayan")
    _names_run(client, db, [page])
    made = _entities(client)
    assert set(made) == {"Popayán"}, made.keys()
    assert set(made["Popayán"]["aliases"]) == {"Ciudad de Popayán", "Ciudad de Popayan"}
    assert _pairs(client) == []
