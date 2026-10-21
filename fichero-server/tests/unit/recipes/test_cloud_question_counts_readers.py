"""The cloud question counts the cloud vision readers (`source.onboard.cloud-question-counts-readers`; #4951, #5768, #5922).

WHY: Set Up asked "Allow pages to be sent to a cloud service" only when a cloud TEXT model could do a job of the plan, so a project
whose steps are Find Lines and Read, with no Correct step, was never asked and no cloud reader could be offered."""
from __future__ import annotations

import pytest

ANSWERS = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"], "mac_memory_gb": 32}


@pytest.fixture
def claude_row(app_db):
    from fichero_server.models import Model, Provider, ProviderType

    row = app_db.save_provider(Provider(name="Anthropic", provider_type=ProviderType("anthropic")))
    app_db.save_model(Model(provider_id=row.id, name="Claude Sonnet", model_id="claude-sonnet-4-5"))
    return row


def _assemble(client):
    r = client.post("/api/recipes/assemble", json=ANSWERS)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_cloud_vision_reader_makes_the_read_step_a_cloud_option(client, with_material, claude_row):
    recipe = _assemble(client)
    assert "read-a-line" in recipe["cloud_options"], recipe["cloud_options"]
    assert any(o["job"] == "read-a-line" and "the page pictures" in o["sentence"] for o in recipe["cloud_offer"])


def test_with_no_provider_row_no_reader_is_counted_and_the_question_is_not_asked_for_it(client, with_material, app_db):
    recipe = _assemble(client)
    assert "read-a-line" not in recipe["cloud_options"], recipe["cloud_options"]
