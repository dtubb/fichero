"""An attribute's value cites where it came from; a kind is a proposed prototype (#5600).

Spec: `docs/contributor_manual/specs/source/source-model.md`, "Extracted data, integrated (review
2026-10-07)":

- `source.extract.attributes-cite`: a value a run sets cites the run it came from
  (`metadata.attribute_sources`); a person's value cites nothing and outranks a machine's.
- `source.extract.kinds-proposed-as-prototypes`: `classify`'s answer is the node's prototype, assigned
  through the audited `document.assign_prototype`, not only a 'classification' artifact.

Each run goes through the REAL background runner with only the model stubbed; the result is read where a
person's window reads it (`GET /api/documents/{id}`, `GET /api/documents/{id}/effective-attributes`), and a
person's choices are made through the routes (`PUT /api/documents/{id}`, `PUT /api/documents/{id}/prototype`).
"""

from __future__ import annotations

import json

import pytest
from PIL import Image

import fichero_server.llm as llm_module
from fichero_server.models import Artifact, DocType, Document, FileType
from tests.unit.workflows.test_default_workflow_e2e_harness import _install_deterministic_workflow_stubs
from tests.unit.workflows.test_text_outputs_are_readings import _run_one_tool

import fichero_server.workflows.tools  # noqa: F401

PAGE = "folio-1"
OTHER_MODEL = {"model_name": "google/gemini-3-flash-preview"}


@pytest.fixture(autouse=True)
def _no_seeding(monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")


@pytest.fixture
def page(test_package, db, tmp_path):
    image = tmp_path / "folio-1.png"
    Image.new("RGB", (32, 32), "white").save(image)
    db.save(Document(id=PAGE, name="folio-1.png", path=str(image), doc_type=DocType.file,
                     file_type=FileType.image, page_content="En la villa de madrid a veynte dias"))
    return test_package


def _model_says(monkeypatch, answer: str) -> None:
    async def fake_vision(*, images, prompt, config, language=None, **kwargs):
        return answer

    monkeypatch.setattr(llm_module, "vision", fake_vision)


def _get(client, path: str) -> dict:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return response.json()


def _sources(client) -> dict:
    return (_get(client, f"/api/documents/{PAGE}")["metadata"] or {}).get("attribute_sources") or {}


def _record(db, artifact_type: str, run: str) -> Artifact:
    made = [a for a in db.query(Artifact, document_id=PAGE)
            if a.artifact_type == artifact_type and (a.run_id or "").startswith(run)]
    assert len(made) == 1, f"expected one {artifact_type} record of {run}, got {made!r}"
    return made[0]


# ── source.extract.kinds-proposed-as-prototypes ─────────────────────────────


def test_classify_proposes_the_kind_as_the_prototype_citing_its_run(page, client, db, monkeypatch):
    _install_deterministic_workflow_stubs(monkeypatch)
    _model_says(monkeypatch, "Letter")

    _run_one_tool(page, "classify-letter", "classify", {})

    doc = _get(client, f"/api/documents/{PAGE}")
    assert doc["prototype_key"] == "letter", "the kind is the page's prototype, not only an artifact"
    effective = _get(client, f"/api/documents/{PAGE}/effective-attributes")
    assert effective["prototype_key"] == "letter"
    record = _record(db, "classification", "classify-letter")
    source = _sources(client)["prototype"]
    assert source["by"] == "machine"
    assert source["run_id"] == record.run_id
    assert source["artifact_id"] == record.id, "the kind cites the run's record of the answer"
    assert source["said"] == "Letter", "and what the model said"
    assert source["model"] == record.model
    prototypes = _get(client, "/api/classifications?dimension=document_prototype")
    items = prototypes["items"] if isinstance(prototypes, dict) else prototypes
    assert "letter" in {item["key"] for item in items}, "the proposed kind is a prototype of the project"


def test_a_kind_a_person_chose_is_never_replaced_by_a_run(page, client, db, monkeypatch):
    _install_deterministic_workflow_stubs(monkeypatch)
    made = client.post("/api/classifications", json={"dimension": "document_prototype", "key": "deed",
                                                       "label": "Deed"})
    assert made.status_code in (200, 201), made.text
    chose = client.put(f"/api/documents/{PAGE}/prototype", json={"prototype_key": "deed"})
    assert chose.status_code == 200, chose.text
    assert _sources(client)["prototype"] == {"by": "person"}, "a person's kind cites nothing"

    _model_says(monkeypatch, "Letter")
    _run_one_tool(page, "classify-over-a-person", "classify", {})

    assert _get(client, f"/api/documents/{PAGE}")["prototype_key"] == "deed"
    assert _sources(client)["prototype"] == {"by": "person"}
    _record(db, "classification", "classify-over-a-person")  # the run happened and kept its record


def test_a_kind_a_run_proposed_is_replaced_by_a_later_run(page, client, db, monkeypatch):
    _install_deterministic_workflow_stubs(monkeypatch)
    _model_says(monkeypatch, "Letter")
    _run_one_tool(page, "classify-first", "classify", {})
    _model_says(monkeypatch, "Receipt")
    _run_one_tool(page, "classify-second", "classify", OTHER_MODEL)

    assert _get(client, f"/api/documents/{PAGE}")["prototype_key"] == "receipt"
    assert _sources(client)["prototype"]["run_id"] == _record(db, "classification", "classify-second").run_id


# ── source.extract.attributes-cite ──────────────────────────────────────────

SCENE = {"scene": "outdoor_urban", "lighting": "natural, bright", "time_of_day": "day"}


def test_scene_writes_page_attributes_that_cite_the_run(page, client, db, monkeypatch):
    _install_deterministic_workflow_stubs(monkeypatch)
    _model_says(monkeypatch, json.dumps(SCENE))

    _run_one_tool(page, "scene-run", "scene", {})

    values = _get(client, f"/api/documents/{PAGE}/effective-attributes")["values"]
    assert values["scene"] == "outdoor_urban"
    assert values["scene_lighting"] == "natural, bright"
    assert values["scene_time_of_day"] == "day"
    assert "attribute_sources" not in values, "the sources are not shown as fields"
    record = _record(db, "scene", "scene-run")
    sources = _sources(client)
    for key in ("scene", "scene_lighting", "scene_time_of_day"):
        assert sources[key]["by"] == "machine"
        assert sources[key]["run_id"] == record.run_id
        assert sources[key]["artifact_id"] == record.id


def test_a_persons_attribute_is_never_overwritten_by_a_later_run(page, client, db, monkeypatch):
    _install_deterministic_workflow_stubs(monkeypatch)
    _model_says(monkeypatch, json.dumps(SCENE))
    _run_one_tool(page, "scene-first", "scene", {})

    attributes = _get(client, f"/api/documents/{PAGE}")["attributes"]
    edited = client.put(f"/api/documents/{PAGE}", json={"attributes": {**attributes, "scene": "studio"}})
    assert edited.status_code == 200, edited.text
    assert _sources(client)["scene"] == {"by": "person"}
    assert _sources(client)["scene_lighting"]["by"] == "machine", "only the key the person changed is theirs"

    _model_says(monkeypatch, json.dumps({**SCENE, "lighting": "artificial, dim"}))
    _run_one_tool(page, "scene-second", "scene", OTHER_MODEL)

    values = _get(client, f"/api/documents/{PAGE}/effective-attributes")["values"]
    assert values["scene"] == "studio", "a run overwrote a person's value"
    assert _sources(client)["scene"] == {"by": "person"}
    # The run did write: the machine's own value moved on, citing the later run.
    assert values["scene_lighting"] == "artificial, dim"
    assert _sources(client)["scene_lighting"]["run_id"] == _record(db, "scene", "scene-second").run_id


def test_a_value_already_on_the_page_that_no_run_set_is_kept(page, client, db, monkeypatch):
    """A value from before attributes cited (an import, an older edit) is treated as a person's."""
    _install_deterministic_workflow_stubs(monkeypatch)
    doc = db.get(Document, PAGE)
    db.save(doc.model_copy(update={"attributes": {"scene": "aerial"}}))
    _model_says(monkeypatch, json.dumps(SCENE))

    _run_one_tool(page, "scene-over-old", "scene", {})

    values = _get(client, f"/api/documents/{PAGE}/effective-attributes")["values"]
    assert values["scene"] == "aerial"
    assert "scene" not in _sources(client)
    assert values["scene_lighting"] == "natural, bright"
