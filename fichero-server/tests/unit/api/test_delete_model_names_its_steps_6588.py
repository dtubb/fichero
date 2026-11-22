"""`models.manage.delete-a-model` (#6588, #6747): deleting a downloaded model that a step of the open project's recipe uses is
refused with the step named until the person confirms; with nothing using it, or confirmed, it deletes and says what it freed."""
from __future__ import annotations

from unittest.mock import MagicMock

from fichero_server.recipes.discovery import steps_using_model

RECIPE = {"overrides": [{"step": "read", "card": "mlx:hf/acme/reader@main"}, {"step": "names", "card": "spacy:en_core_web_sm"},
                        {"step": "other", "card": "whisper:database"}]}


def test_steps_using_a_model_match_the_whole_id_never_a_part_of_one():
    assert steps_using_model("acme/reader", RECIPE) == ["read"]
    assert steps_using_model("en_core_web_sm", RECIPE) == ["names"]
    assert steps_using_model("base", RECIPE) == [], "'base' is a word inside 'database', not that model"
    assert steps_using_model("acme/reader", None) == []


def _manager(monkeypatch, freed=1234):
    mgr = MagicMock()
    mgr.delete_model.return_value = freed
    monkeypatch.setattr("fichero_server.llm.local_models.LocalModelManager", lambda: mgr)
    monkeypatch.setattr("fichero_server.recipes.project.read_project_setup", lambda library: {"recipe": RECIPE})
    return mgr


def test_a_model_a_step_uses_is_refused_with_the_step_named_until_confirmed(client, monkeypatch):
    mgr = _manager(monkeypatch)
    header = {"X-Fichero-Library-Path": "/tmp/lib.fichero"}
    refused = client.delete("/api/local-models/spacy/en_core_web_sm", headers=header)
    assert refused.status_code == 409 and "names" in refused.json()["detail"]
    mgr.delete_model.assert_not_called()
    done = client.delete("/api/local-models/spacy/en_core_web_sm?confirm=true", headers=header)
    assert done.status_code == 200 and done.json()["freed_bytes"] == 1234
    mgr.delete_model.assert_called_once_with("spacy", "en_core_web_sm")


def test_a_model_no_step_uses_deletes_at_once(client, monkeypatch):
    mgr = _manager(monkeypatch)
    assert client.delete("/api/local-models/whisper/tiny", headers={"X-Fichero-Library-Path": "/tmp/lib.fichero"}).status_code == 200
    mgr.delete_model.assert_called_once_with("whisper", "tiny")
