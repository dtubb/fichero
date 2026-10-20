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
    assert "TrOCR" in card.offered_because and "Kraken" in card.offered_because and "safetensors" in card.offered_because
    monkeypatch.setattr(tr, "is_installed", lambda repo: False)
    assert discovery.candidate_installed(card) is False  # its safetensors download before the run asks for them
    assert discovery.candidate_download(card) == {
        "runtime": "kraken", "model": READER, "action": "model.download",
        "params": {"runtime": "kraken", "model": READER}}


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


# -- safetensors only, at the pinned commit (review 765: a recipe pin names any Hub repo; a pickle would run in the engine) ----
SHA = "d" * 40


def _hub(monkeypatch, files, sha=SHA):
    monkeypatch.setattr(tr, "hub_info", lambda repo: {"sha": sha, "siblings": [{"rfilename": f, "size": 10} for f in files]})


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "_store", lambda: tmp_path)
    return tmp_path


def test_a_repository_with_only_a_pickled_bin_is_refused_in_words_and_nothing_downloads(store, monkeypatch):
    _hub(monkeypatch, ["pytorch_model.bin", "config.json", "training_args.bin"])
    fetched = []
    monkeypatch.setattr(tr, "_snapshot", lambda *a: fetched.append(a))
    with pytest.raises(tr.NoSafetensors, match="no safetensors weights"):
        tr.download(REPO)
    assert fetched == [] and not tr.is_installed(REPO)


def test_the_download_pins_the_commit_and_takes_no_pickled_file(store, monkeypatch):
    _hub(monkeypatch, ["model.safetensors", "config.json", "optimizer.pt", "training_args.bin"])
    seen = []
    monkeypatch.setattr(tr, "_snapshot", lambda repo, revision, cache_dir: seen.append((repo, revision, cache_dir)))
    assert tr.download(REPO) == SHA
    assert seen == [(REPO, SHA, str(store))]
    assert tr.is_installed(REPO) and tr.revision_of(REPO) == SHA
    assert {"*.bin", "*.pt", "*.ckpt", "*.pth"} <= set(tr.PICKLED)  # the snapshot ignores every pickle pattern


def test_the_load_names_the_pinned_commit_demands_safetensors_and_reads_only_what_is_on_this_mac(store, monkeypatch):
    import sys
    import types

    from fichero_server.workflows.tools import economy_htr

    _hub(monkeypatch, ["model.safetensors", "config.json"])
    monkeypatch.setattr(tr, "_snapshot", lambda *a: None)
    calls = {}

    class Model:
        def to(self, device):
            return self

        def eval(self):
            return self

    fake = types.ModuleType("transformers")
    fake.TrOCRProcessor = types.SimpleNamespace(from_pretrained=lambda mid, **kw: calls.setdefault("processor", kw) or object())
    fake.VisionEncoderDecoderModel = types.SimpleNamespace(
        from_pretrained=lambda mid, **kw: (calls.setdefault("model", kw), Model())[1])
    monkeypatch.setitem(sys.modules, "transformers", fake)
    monkeypatch.setitem(sys.modules, "torch", types.ModuleType("torch"))
    economy_htr._TROCR_CACHE.clear()
    economy_htr._load_trocr(REPO)
    for kw in (calls["processor"], calls["model"]):
        assert kw["revision"] == SHA and kw["local_files_only"] is True
    assert calls["model"]["use_safetensors"] is True


def test_a_bin_only_repository_is_never_loaded(store, monkeypatch):
    import sys
    import types

    from fichero_server.workflows.tools import economy_htr

    _hub(monkeypatch, ["pytorch_model.bin"])
    loaded = []
    fake = types.ModuleType("transformers")
    fake.TrOCRProcessor = types.SimpleNamespace(from_pretrained=lambda *a, **k: loaded.append("processor"))
    fake.VisionEncoderDecoderModel = types.SimpleNamespace(from_pretrained=lambda *a, **k: loaded.append("model"))
    monkeypatch.setitem(sys.modules, "transformers", fake)
    monkeypatch.setitem(sys.modules, "torch", types.ModuleType("torch"))
    economy_htr._TROCR_CACHE.clear()
    with pytest.raises(tr.NoSafetensors):
        economy_htr._load_trocr(REPO)
    assert loaded == []


def test_a_trocr_model_not_yet_downloaded_is_listed_in_missing_models_so_the_run_asks_first(store):
    from fichero_server.recipes import start

    run = {"provider_override": "kraken", "model_override": READER, "steps": ["read"], "card": "x"}
    [offer] = start.missing_models([run])
    assert offer["model"] == READER and offer["runtime"] == "kraken" and offer["action"] == "model.download"
    assert REPO in offer["name"] and offer["steps"] == ["read"]


def test_the_download_job_accepts_the_trocr_reader_id():
    from fichero_server.llm import kraken_runtime as kr

    assert kr.recognition_spec(READER) == {"trocr": REPO}
    assert kr.recognition_display_name(READER) == "trocr-traditional-chinese-historical-finetune"


def test_economy_htr_reads_on_the_cpu_by_default(monkeypatch):
    import sys
    import types

    from fichero_server.core import compute_preferences as cp
    from fichero_server.workflows.tools import economy_htr

    monkeypatch.setattr(cp, "compute_preferences", lambda: {"device": "auto"})
    monkeypatch.setattr(tr, "ensure", lambda repo: SHA)
    seen = {}

    class Model:
        def to(self, device):
            seen["device"] = device
            return self

        def eval(self):
            return self

    fake = types.ModuleType("transformers")
    fake.TrOCRProcessor = types.SimpleNamespace(from_pretrained=lambda *a, **k: object())
    fake.VisionEncoderDecoderModel = types.SimpleNamespace(from_pretrained=lambda *a, **k: Model())
    monkeypatch.setitem(sys.modules, "transformers", fake)
    monkeypatch.setitem(sys.modules, "torch", types.ModuleType("torch"))
    economy_htr._TROCR_CACHE.clear()
    economy_htr._load_trocr(REPO)
    assert seen["device"] == "cpu"
