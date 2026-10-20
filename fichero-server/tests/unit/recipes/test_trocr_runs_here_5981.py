"""A TrOCR model on the Hub reads the lines Kraken found, here, with the bundled torch and transformers
(`source.onboard.model-search-trocr-runs-here`, #5981). No network and no model: the TrOCR call is faked; the crop of each line,
the reader's id, the card the search makes, the plan's reader override and the read onto the page's working lines are real."""

from __future__ import annotations

import asyncio

import pytest
from PIL import Image

from fichero_server.llm import trocr_runtime as tr
from fichero_server.recipes import cards, discovery

REPO = "ZihCiLin/trocr-traditional-chinese-historical-finetune"
READER = "trocr-hf-ZihCiLin--trocr-traditional-chinese-historical-finetune"
LISTING = {"id": REPO, "modelId": REPO, "pipeline_tag": "image-to-text", "downloads": 61, "library_name": "transformers",
           "tags": ["transformers", "safetensors", "vision-encoder-decoder", "trocr", "ocr", "image-to-text", "zh",
                    "license:apache-2.0"]}


def test_a_trocr_reader_has_an_id_that_names_its_repository():
    assert tr.reader_id_for_trocr(REPO) == READER
    assert tr.repo_of(READER) == REPO and tr.repo_of("kraken-mccatmus") is None
    with pytest.raises(ValueError):
        tr.reader_id_for_trocr("a--b/model")


def test_each_line_is_cut_from_the_page_by_its_outline_and_read_in_order(tmp_path, monkeypatch):
    page = tmp_path / "p.png"
    Image.new("RGB", (400, 300), "white").save(page)
    seen = []

    def fake(crop_paths, model_id, batch_size=8):
        seen.append((model_id, [Image.open(p).size for p in crop_paths]))
        return [f"line {i}" for i in range(len(crop_paths))]

    monkeypatch.setattr("fichero_server.workflows.tools.economy_htr.trocr_transcribe_lines", fake)
    lines = [{"id": "a", "polygon": [[20, 20], [380, 20], [380, 60], [20, 60]]},
             {"id": "b", "polygon": [[20, 80], [380, 80], [380, 120], [20, 120]]}]
    assert tr.read_lines(str(page), REPO, lines) == ["line 0", "line 1"]
    model_id, sizes = seen[0]
    assert model_id == REPO and len(sizes) == 2 and all(h < 300 and w <= 400 for w, h in sizes)  # lines, not the page


def test_a_line_with_no_outline_reads_as_empty_and_is_not_sent(tmp_path, monkeypatch):
    page = tmp_path / "p.png"
    Image.new("RGB", (400, 300), "white").save(page)
    monkeypatch.setattr("fichero_server.workflows.tools.economy_htr.trocr_transcribe_lines",
                        lambda paths, model_id, batch_size=8: [f"t{i}" for i in range(len(paths))])
    lines = [{"id": "a", "polygon": []}, {"id": "b", "polygon": [[20, 80], [380, 80], [380, 120], [20, 120]]}]
    assert tr.read_lines(str(page), REPO, lines) == ["", "t0"]


def test_the_search_makes_a_trocr_card_that_runs_on_this_mac(monkeypatch):
    async def fake(**kw):
        return [LISTING] if kw.get("task") == "image-to-text" and not kw.get("search") else []

    monkeypatch.setattr("fichero_server.api.routes.ai.models._fetch_hf_models", fake)
    found, _ = asyncio.run(discovery.search_hugging_face(frozenset({"zh"})))
    card = next(c for c in found if c.pin.get("trocr") == REPO)
    assert card.runs_here and card.local and card.jobs == discovery.READER_JOBS
    assert "TrOCR" in card.offered_because and "Kraken" in card.offered_because
    assert discovery.candidate_installed(card) is None  # it downloads when first used, as the card says
    assert "first used" in discovery.candidate_availability(card)[1]


def test_the_plan_reads_with_it_as_a_reader_override():
    from fichero_server.recipes import start

    assert cards.kraken_reader_for({"trocr": REPO}) == READER
    run = start._reading_run("read-a-line", {"trocr": REPO})
    assert (run["provider_override"], run["model_override"]) == ("kraken", READER)


def test_where_it_runs_says_this_mac_only_with_the_reason_for_the_rest():
    from fichero_server.recipes.where_it_runs import places_it_can_run

    card = discovery._trocr_hub_card(LISTING, "an OCR model (image-to-text)", frozenset({"zh"}))
    got = {o["place"]: o for o in places_it_can_run(card, this_mac_gb=16, hf_ready=True, clusters=["acenet"])}
    assert got["this-mac"]["can"] and "transformers" in got["this-mac"]["needs"]
    assert not got["hf-jobs"]["can"] and "TrOCR" in got["hf-jobs"]["why"]


@pytest.mark.asyncio
async def test_the_transcribe_tool_reads_the_pages_working_lines_with_it(page, monkeypatch):
    """Through the real Transcribe tool on the 5654 page (Kraken found and read three lines): the TrOCR reader's texts become
    the lines' readings; Kraken's recogniser is not asked."""
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.transcribe import transcribe
    from tests.unit.workflows.test_review_corrects_the_lines_5654 import _counting

    monkeypatch.setattr(tr, "read_lines", lambda image_path, repo, lines: ["uno", "dos", "tres"])
    done = await transcribe(
        inputs={"files": page["src"]["files"], "documents": page["src"]["documents"], "vision_mode": "kraken",
                "regions_first": False, "kraken_model": READER},
        state={"library_path": page["library"], "task_id": None}, llm_config=LLMConfig(provider="", model=""))
    assert not done.get("error"), done.get("error")
    assert _counting(page) == ["uno", "dos", "tres"]


from tests.unit.workflows.test_review_corrects_the_lines_5654 import page  # noqa: E402,F401  (the page fixture is theirs)
