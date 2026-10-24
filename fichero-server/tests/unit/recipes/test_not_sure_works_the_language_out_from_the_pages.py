"""`source.onboard.project.about-material`: "Not sure" is sent as languages ['und'] with no script; the engine works the language
and script out from the sample pages, says so in `inferred_language`, and still plans a model for every step (Test 13)."""
from __future__ import annotations

from types import SimpleNamespace

from fichero_server.api.routes.system import recipes as routes
from fichero_server.recipes import language_guess, samples

SPANISH = ("El dicho escribano de la ciudad dijo que por cuanto los vecinos de esta villa no han pagado lo que deben "
           "a su majestad, se les notifique para que con el tiempo pasado lo cumplan como es justo y no se haga otra cosa. ") * 2
CREE = "ᓀᐦᐃᔭᐍᐏᐣ ᐊᓂᒥᑑ ᐃᔨᔫ ᐊᔭᒥᐁᐎᓐ ᒥᓯᐌ ᓀᐦᐃᔭᐍᐏᐣ ᐊᓂᒥᑑ ᐃᔨᔫ ᐊᔭᒥᐁᐎᓐ ᒥᓯᐌ ᓀᐦᐃᔭᐍᐏᐣ ᐊᓂᒥᑑ"


def test_script_and_language_come_from_the_letters_and_function_words():
    assert language_guess.script_of(SPANISH) == "Latn" and language_guess.language_of(SPANISH) == "es"
    assert language_guess.script_of(CREE) == "Cans" and language_guess.language_of(CREE) is None
    assert language_guess.script_of("a b") is None, "too few letters to say"


def _db(texts):
    pages = {f"p{i}": SimpleNamespace(id=f"p{i}", page_content=t, path=None) for i, t in enumerate(texts)}
    return SimpleNamespace(get=lambda _model, i: pages.get(i)), list(pages)


def test_infer_says_what_the_pages_hold_in_one_sentence(monkeypatch, tmp_path):
    db, ids = _db([SPANISH])
    monkeypatch.setattr(samples, "_chosen", lambda _db: {"pages": [{"id": i} for i in ids]})
    found = language_guess.infer(db, tmp_path)
    assert (found["code"], found["script"], found["from"]) == ("es", "Latn", "pages")
    assert found["sentence"].startswith("Language worked out from your pages: Spanish") and "Change it" in found["sentence"]


def test_infer_with_pages_that_do_not_say_names_nothing_and_says_so(monkeypatch, tmp_path):
    db, ids = _db(["", ""])
    monkeypatch.setattr(samples, "_chosen", lambda _db: {"pages": [{"id": i} for i in ids]})
    found = language_guess.infer(db, tmp_path)
    assert found["code"] is None and found["script"] is None and "Could not tell" in found["sentence"]


def test_unsure_is_und_alone_with_no_script():
    assert language_guess.unsure({"languages": ["und"]})
    assert not language_guess.unsure({"languages": ["und"], "scripts": ["Latn"]})
    assert not language_guess.unsure({"languages": ["es"]})


def test_a_plan_with_not_sure_still_proposes_a_model_for_every_step():
    recipe = routes._assemble({"purposes": ["search"], "materials": ["handwriting"], "languages": ["und"], "scripts": []})
    models = {s["job"]: s.get("model") for s in recipe["steps"] if s["job"] in ("find-lines", "read-a-line")}
    assert models["find-lines"] == {"kraken": "blla", "kraken_version": "5.2"} or models["find-lines"], models
    assert all(models.values()), models
    assert recipe["gaps"] == []


def test_the_guess_is_kept_per_sample_set_and_read_again_when_the_samples_change(monkeypatch, tmp_path):
    db, ids = _db([SPANISH])
    monkeypatch.setattr(samples, "_chosen", lambda _db: {"pages": [{"id": i} for i in ids]})
    reads = []
    real = language_guess._page_text
    monkeypatch.setattr(language_guess, "_page_text", lambda *a: reads.append(1) or real(*a))
    language_guess._KEPT.clear()
    first = language_guess.infer(db, tmp_path)
    assert language_guess.infer(db, tmp_path) == first and len(reads) == 1, "a second assemble does not read the pages again"
    db2, ids2 = _db([SPANISH, SPANISH])
    monkeypatch.setattr(samples, "_chosen", lambda _db: {"pages": [{"id": i} for i in ids2]})
    language_guess.infer(db2, tmp_path)
    assert len(reads) == 3, "a different sample set is read again"


def test_assemble_through_a_project_says_what_was_worked_out(client, with_material):
    """The library path: the route reads the project's own sample pages and answers with `inferred_language` (code or null, always a sentence)."""
    language_guess._KEPT.clear()
    r = client.post("/api/recipes/assemble", json={"purposes": ["search"], "materials": ["handwriting"], "languages": ["und"], "scripts": []})
    assert r.status_code == 200, r.text
    found = r.json()["inferred_language"]
    assert found["from"] == "pages" and found["sentence"] and set(found) == {"code", "name", "script", "from", "sentence"}
    assert all(s["model"] for s in r.json()["steps"] if s["job"] in ("find-lines", "read-a-line"))
    plain = client.post("/api/recipes/assemble", json={"purposes": ["search"], "materials": ["handwriting"], "languages": ["es"], "scripts": ["Latn"]})
    assert plain.json()["inferred_language"] is None


def test_a_known_language_still_needs_a_script_only_not_sure_may_leave_it_out(client, with_material):
    bad = client.post("/api/recipes/assemble", json={"purposes": ["search"], "materials": ["handwriting"], "languages": ["es"], "scripts": []})
    assert bad.status_code == 422 and "scripts" in bad.text
