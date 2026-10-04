"""Setup works things out rather than asking (`source.onboard.derives-not-asks`).

Spec (source/models-chains-and-projects.md): "direction, line position, fonts, this Mac's chip and
memory, keys present and compute targets are worked out, shown, and correctable, never asked."

WHY: every question setup asks that Fichero could have answered is friction, and a wrong silent
guess is worse: so each derived fact is returned WITH where it came from, for setup to show and the
person to correct. Tested through the route setup calls.
"""
from __future__ import annotations


def _derived(client, scripts):
    r = client.get("/api/recipes/derived", params={"scripts": ",".join(scripts)})
    assert r.status_code == 200, r.text
    return r.json()


def test_each_script_gets_its_direction_and_says_where_from(client):
    by = {s["script"]: s for s in _derived(client, ["Arab", "Latn", "Jpan"])["scripts"]}
    assert by["Arab"]["direction"] == "rtl" and "Arab" in by["Arab"]["direction_from"]
    assert by["Latn"]["direction"] == "ltr"
    # Japanese may be written vertically: that is not derivable from the script, so setup must ask.
    assert by["Jpan"]["may_be_vertical"] is True and by["Latn"]["may_be_vertical"] is False


def test_a_script_macos_lacks_gets_fichero_s_bundled_font(client):
    by = {s["script"]: s for s in _derived(client, ["Syrc", "Syrj", "Cher", "Latn"])["scripts"]}
    assert by["Syrc"]["font"] == "Noto Sans Syriac"
    assert by["Syrj"]["font"] == "Noto Sans Syriac Western"
    assert by["Cher"]["font"] == "Noto Sans Cherokee"
    assert by["Latn"]["font"] is None and "system" in by["Latn"]["font_from"]


def test_this_mac_keys_and_places_to_run_are_reported_without_secrets(client, monkeypatch):
    import fichero_server.recipes.derived as derived

    monkeypatch.setattr(derived, "_providers_with_keys", lambda: ["openrouter", "huggingface"])
    body = _derived(client, ["Latn"])
    assert body["mac"]["memory_gb"] is None or body["mac"]["memory_gb"] > 0
    assert body["keys"] == ["openrouter", "huggingface"]  # names only: a key itself never leaves the engine
    places = [t["id"] for t in body["targets"]]
    assert places[0] == "this-mac" and "huggingface" in places


def test_no_hugging_face_target_without_its_key(client, monkeypatch):
    import fichero_server.recipes.derived as derived

    monkeypatch.setattr(derived, "_providers_with_keys", lambda: [])
    assert [t["id"] for t in _derived(client, ["Latn"])["targets"]] == ["this-mac"]


def test_an_unknown_script_code_is_refused_by_name(client):
    r = client.get("/api/recipes/derived", params={"scripts": "Latn,Zzzz,Nope"})
    assert r.status_code == 422 and "Nope" in r.text
