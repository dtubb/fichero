"""Set Up's model search names the script, ranks specialists over general readers, reads the card and says what to do when it
finds nothing (#5970; spec `source.onboard.model-search-*`). The Hub is a recorded listing; nothing touches the network."""

import asyncio

import pytest

from fichero_server.recipes import discovery


def _model(repo, task="image-to-text", tags=(), downloads=0):
    return {"modelId": repo, "pipeline_tag": task, "tags": ["mlx", *tags], "library_name": "mlx", "downloads": downloads}


GLM = _model("zai-org/GLM-OCR-4bit", tags=["ocr", "ar", "zh"], downloads=1_700_000)
DETECTOR = _model("PaddlePaddle/PP-OCRv5_server_det", tags=["ocr", "ar"], downloads=900_000)
ORIENTATION = _model("PaddlePaddle/PP-LCNet_x1_0_doc_ori", tags=["ocr", "ar"], downloads=500_000)
ARABIC_HTR = _model("someone/arabic-manuscript-htr", tags=["htr", "handwritten", "manuscripts", "ar"], downloads=30)


@pytest.fixture
def hub(monkeypatch):
    """A Hub that answers every query with the same recorded listing; returns the log of what was asked."""
    asked = []

    async def fetch(task=None, search=None, sort="downloads", limit=20, offset=0, library=None, tags=None):
        asked.append({"task": task, "search": search, "tags": list(tags or [])})
        return [GLM, DETECTOR, ORIENTATION, ARABIC_HTR]

    async def card(repo):
        if "arabic" in repo:
            return "---\nlicense: apache-2.0\nlanguage: [ar]\nmodel-index:\n- results:\n  - metrics:\n    - {type: cer, value: 4.2}\n---\ntext"
        return "---\nlicense: mit\n---\nA general OCR model."

    monkeypatch.setattr("fichero_server.api.routes.ai.models._fetch_hf_models", fetch)
    monkeypatch.setattr(discovery, "_fetch_card_text", card)
    monkeypatch.setattr(discovery, "_catalogue_repo", lambda repo: False)
    return asked


def test_the_tags_asked_for_include_the_ones_models_of_the_language_carry():
    assert discovery.language_tags(frozenset({"ota"})) == ["ota", "ott"]
    assert discovery.language_tags(frozenset({"cu", "he"})) == ["cu", "chu", "he"]
    assert discovery.language_tags(frozenset({"zh-Hant"})) == ["zh"]


def test_the_names_searched_include_the_language_and_the_script_not_only_the_nine():
    ottoman = discovery.search_words(frozenset({"ota"}))
    assert "ottoman" in ottoman and "arabic" in ottoman
    assert "hebrew" in discovery.search_words(frozenset({"he"}))
    assert "chinese" in discovery.search_words(frozenset({"zh"}))
    assert "spanish" in discovery.search_words(frozenset({"es"}))  # the nine are still there
    assert not {"old", "modern", "language"} & set(discovery.search_words(frozenset({"ota"})))


def test_an_ottoman_project_asks_the_hub_for_ott_and_for_ottoman(hub):
    asyncio.run(discovery.search_hugging_face(frozenset({"ota"})))
    assert any("ott" in q["tags"] for q in hub), "no query by the tag models of Ottoman Turkish carry"
    assert any(q["search"] == "ottoman" for q in hub), "no query by the name ottoman"
    assert any(q["search"] == "arabic" for q in hub), "no query by the script's name"


def test_a_detector_and_an_orientation_part_are_not_readers():
    assert discovery.reads_text(DETECTOR) is None and discovery.reads_text(ORIENTATION) is None
    assert discovery.reads_text(ARABIC_HTR) is not None and discovery.reads_text(GLM) is not None


def test_an_arabic_handwriting_reader_ranks_above_a_general_ocr_model_with_a_million_downloads(hub):
    cards, _ = asyncio.run(discovery.search_hugging_face(frozenset({"ar"})))
    repos = [c.pin["hf"] for c in cards]
    assert repos[0] == "someone/arabic-manuscript-htr"
    assert "zai-org/GLM-OCR-4bit" in repos
    assert not [r for r in repos if r.endswith("_det") or r.endswith("_ori")]


def test_the_top_cards_are_read_and_say_their_cer_or_that_they_state_none(hub):
    cards, _ = asyncio.run(discovery.search_hugging_face(frozenset({"ar"})))
    by = {c.pin["hf"]: c for c in cards}
    assert "CER 4.2% on its own material" in by["someone/arabic-manuscript-htr"].offered_because
    assert by["someone/arabic-manuscript-htr"].cer_published == pytest.approx(0.042)
    assert "states no measurement: unmeasured" in by["zai-org/GLM-OCR-4bit"].offered_because
    assert by["zai-org/GLM-OCR-4bit"].cer_published is None


def test_a_card_that_cannot_be_fetched_is_said_unmeasured(hub, monkeypatch):
    async def none(repo):
        return None

    monkeypatch.setattr(discovery, "_fetch_card_text", none)
    cards, _ = asyncio.run(discovery.search_hugging_face(frozenset({"ar"})))
    assert all("could not be read: unmeasured" in c.offered_because for c in cards)


@pytest.mark.parametrize("text, cer", [
    ("---\nmodel-index:\n- results:\n  - metrics:\n    - {type: cer, value: 0.031}\n---\n", 0.031),
    ("---\nmodel-index:\n- results:\n  - metrics:\n    - {name: Character Error Rate, value: 12.5}\n---\n", 0.125),
    ("# Model\nWe report CER: 3.1 % on the test set.", 0.031),
    ("---\nlicense: mit\n---\nNo numbers here.", None),
    ("---\n: : broken: [\n---\nCER is great", None),
])
def test_a_cer_is_read_only_where_the_card_states_one(text, cer):
    assert discovery.parse_card_text(text)["cer"] == cer


def test_the_card_gives_its_licence_languages_and_datasets():
    got = discovery.parse_card_text("---\nlicense: cc-by-4.0\nlanguage: [ar, fa]\ndatasets: [muharaf]\n---\nx")
    assert got["licence"] == "cc-by-4.0" and got["languages"] == ["ar", "fa"] and got["datasets"] == ["muharaf"]


def test_when_nothing_is_found_the_words_say_what_a_person_can_do():
    said = discovery.nothing_found_words(frozenset({"lzh"}))
    assert said.startswith("No model that reads ") and "train one from about a hundred lines you correct" in said
    assert "cloud reader" in said


def test_slavonic_hanzi_and_guji_are_searched_for_the_languages_that_models_name_that_way():
    assert "slavonic" in discovery.search_words(frozenset({"cu"}))  # the ISO name is Church Slavic
    assert {"hanzi", "guji"} <= set(discovery.search_words(frozenset({"lzh"})))
    assert "aramaic" in discovery.search_words(frozenset({"syc"}))


def test_a_qualifier_in_a_language_name_is_not_a_search_word():
    words = discovery.search_words(frozenset({"zh", "ota", "cu"}))
    assert not {"official", "literary", "dialect", "regional"} & set(words)


def test_the_step_search_asks_for_the_aliases_too(monkeypatch):
    asked = []

    async def fetch(task=None, search=None, sort="downloads", limit=20, offset=0, library=None, tags=None):
        asked.append(list(tags or []))
        return []

    monkeypatch.setattr("fichero_server.api.routes.ai.models._fetch_hf_models", fetch)
    job = next(iter(discovery.STEP_SEARCHES))
    asyncio.run(discovery.search_hugging_face_for_step(job, frozenset({"ota"})))
    assert any("ott" in tags for tags in asked) and any("ota" in tags for tags in asked)


def test_the_cards_are_fetched_together_and_a_card_is_capped(hub, monkeypatch):
    import time

    started = []

    async def slow(repo):
        started.append(time.monotonic())
        await asyncio.sleep(0.2)
        return "x" * 10

    monkeypatch.setattr(discovery, "_fetch_card_text", slow)
    began = time.monotonic()
    asyncio.run(discovery.search_hugging_face(frozenset({"ar"})))
    assert len(started) == 2 and max(started) - min(started) < 0.15, "fetched one after another"
    assert time.monotonic() - began < 0.38, "two 0.2 s fetches took as long as in a row"
    assert discovery.CARD_BYTES <= 100_000
