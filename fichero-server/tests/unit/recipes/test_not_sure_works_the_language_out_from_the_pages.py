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
    recipe = routes._assemble({"purposes": ["search"], "materials": ["handwriting"], "languages": ["und"]})
    models = {s["job"]: s.get("model") for s in recipe["steps"] if s["job"] in ("find-lines", "read-a-line")}
    assert models["find-lines"] == {"kraken": "blla", "kraken_version": "5.2"} or models["find-lines"], models
    assert all(models.values()), models
    assert recipe["gaps"] == []
