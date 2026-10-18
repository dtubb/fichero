"""The font transcription text is drawn in comes from the script and period setup derived, and a person's
choice is remembered per library (`layers.text.font-from-script-and-period`, #5438).

WHY: Latin was "the system font draws it", so a medieval Latin project (MUFI letters, long s) got no
Junicode unless the app guessed; nothing stored the answer, so a pane's choice could not be remembered.
Tested through the routes the app calls.
"""
from __future__ import annotations


def _font(client, script="Latn", **params):
    r = client.get("/api/recipes/derived", params={"scripts": script, **params})
    assert r.status_code == 200, r.text
    return r.json()["scripts"][0]


def test_medieval_latin_defaults_to_junicode_and_says_why(client):
    fact = _font(client, period="12th century")
    assert fact["font"] == "Junicode" and "medieval" in fact["font_from"]


def test_a_later_period_or_none_leaves_latin_to_the_system(client):
    assert _font(client, period="18th century")["font"] is None
    assert _font(client)["font"] is None


def test_the_period_is_read_from_the_saved_setup_when_not_sent(client):
    r = client.put("/api/recipes/project", json={"answers": {"purposes": ["search"], "languages": ["la"],
                                                             "scripts": ["Latn"], "period": "1250"}})
    assert r.status_code == 200, r.text
    assert _font(client)["font"] == "Junicode"


def test_a_pane_choice_is_stored_per_library_and_wins(client):
    r = client.put("/api/recipes/font", json={"script": "Latn", "font": "Noto Sans Coptic"})
    assert r.status_code == 200, r.text
    fact = _font(client, period="12th century")
    assert fact["font"] == "Noto Sans Coptic" and "chosen" in fact["font_from"]
    # Clearing the choice returns to the derived font.
    assert client.put("/api/recipes/font", json={"script": "Latn", "font": None}).status_code == 200
    assert _font(client, period="12th century")["font"] == "Junicode"


def test_a_font_that_is_not_bundled_is_refused(client):
    r = client.put("/api/recipes/font", json={"script": "Latn", "font": "Comic Sans"})
    assert r.status_code == 422 and "Comic Sans" in r.text


def test_choosing_a_font_is_audited_and_one_undo_restores_it(client):
    """One audited action layer: the choice goes through project.save_setup, so it has an audit row and an undo."""
    assert client.put("/api/recipes/font", json={"script": "Latn", "font": "Noto Sans Coptic"}).status_code == 200
    audit = client.get("/api/actions/audit").json()["items"][0]
    assert audit["action_name"] == "project.save_setup"
    assert client.post(f"/api/actions/audit/{audit['id']}/undo").status_code == 200
    assert _font(client, period="12th century")["font"] == "Junicode"


def test_the_choice_answers_with_the_audit_row_the_app_registers_undo_with(client):
    """#5777: Edit > Undo reverses the choice through the audit row the answer names."""
    r = client.put("/api/recipes/font", json={"script": "Latn", "font": "Noto Sans Coptic"})
    audit = client.get("/api/actions/audit").json()["items"][0]
    assert r.json()["audit_id"] == audit["id"]
