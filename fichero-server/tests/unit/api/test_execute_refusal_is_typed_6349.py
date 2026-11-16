"""`ai.cloud.hand-run-refused-before-it-starts` (#6349, #6028): a hand run refused at the door for images or a cap answers 400
with the typed refusal in `detail`, not a sentence alone. Nothing starts."""
from __future__ import annotations

from fichero_server.api.routes.workflow_execution import core
from fichero_server.llm import EgressRefusedError, spend
from fichero_server.workflows.default_workflows import preset_workflow_id, seed_default_workflows


def _refuse_with(monkeypatch, error):
    def _raise(*args, **kwargs):
        raise error

    monkeypatch.setattr(core, "_validate_workflow_for_execution", _raise)


def test_an_images_refusal_answers_the_typed_refusal_with_four_fixes(client, db, monkeypatch):
    seed_default_workflows(db)
    _refuse_with(monkeypatch, EgressRefusedError("openai", model="gpt", project="/x/P.fichero"))
    r = client.post("/api/workflow-execution/execute", json={"workflow_id": preset_workflow_id("Extract Entities"), "inputs": {}})
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert "was not sent" in detail["message"]
    assert detail["refusal"]["kind"] == "images"
    assert [f["kind"] for f in detail["refusal"]["fixes"]] == ["allow-everywhere", "allow-project", "allow-once", "open-settings"]


def test_a_cap_refusal_answers_the_typed_refusal_too(client, db, monkeypatch, tmp_path):
    seed_default_workflows(db)
    folder = tmp_path / "P.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text("cloud_allowed: true\ncloud_spend_cap_usd: 0\n")
    lib = str(tmp_path / "P.fichero")
    with spend._LOCK:
        over = spend._over_cap(lib, 0.0, 0.1)
    _refuse_with(monkeypatch, spend.CloudSpendRefusedError("capped", spend.cap_refusal(lib, 0.1, over)))
    r = client.post("/api/workflow-execution/execute", json={"workflow_id": preset_workflow_id("Extract Entities"), "inputs": {}})
    assert r.status_code == 400, r.text
    refusal = r.json()["detail"]["refusal"]
    assert refusal["kind"] == "cap-monthly" and [f["kind"] for f in refusal["fixes"]] == ["raise-to", "over-cap-once", "open-settings"]
