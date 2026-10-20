"""A Kraken reader hosted on Hugging Face is a candidate that downloads and runs with the Kraken Fichero ships
(`source.onboard.model-search-kraken-on-hub`): its id, its download into its own folder, its card from the search. No
network: the Hub's file list and the file fetch are faked."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from fichero_server.llm import kraken_runtime as kr
from fichero_server.recipes import cards, discovery

REPO = "small-models-for-glam/kraken-ppocrv6-small"
READER = "kraken-hf-small-models-for-glam--kraken-ppocrv6-small"
LISTING = {"id": REPO, "modelId": REPO, "pipeline_tag": "image-to-text", "downloads": 0, "library_name": "kraken",
           "tags": ["kraken", "handwritten-text-recognition", "htr", "ocr", "multilingual", "image-to-text", "ara", "cat",
                    "safetensors", "license:apache-2.0"]}


@pytest.fixture
def data_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken-data"))
    return tmp_path


def test_a_hub_reader_has_an_id_and_a_spec_and_the_id_names_its_repository():
    assert kr.reader_id_for_hub(REPO) == READER
    assert kr.recognition_spec(READER) == {"hf": REPO}
    with pytest.raises(ValueError):
        kr.reader_id_for_hub("a--b/model")  # the id could not be read back


def test_the_card_pin_names_the_reader_the_download_job_fetches():
    assert cards.kraken_reader_for({"kraken_hf": REPO}) == READER


def test_a_hub_reader_downloads_its_one_model_file_into_its_own_folder(data_home, monkeypatch):
    monkeypatch.setattr(kr, "require_installed", lambda: None)
    monkeypatch.setattr(kr, "hub_files", lambda repo: [
        {"url": f"https://huggingface.co/{repo}/resolve/main/small.safetensors", "size": 7, "revision": "main"}])
    fetched = []

    def fetch(url, dest, *, name, size=None, should_stop=lambda: False, on_bytes=None, **kw):
        fetched.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x" * 7)

    monkeypatch.setattr("fichero_server.llm.model_downloads.fetch_file", fetch)
    kr.download_recognition_model(READER)
    assert fetched == [f"https://huggingface.co/{REPO}/resolve/main/small.safetensors"]
    assert kr.is_recognition_model_installed(READER)
    path, model_id = kr.resolve_recognition_model(READER)
    assert path.endswith(f"{READER}/small.safetensors") and model_id == READER


def test_a_repository_with_two_model_files_is_refused_in_words(data_home, monkeypatch):
    monkeypatch.setattr(kr, "require_installed", lambda: None)
    monkeypatch.setattr(kr, "hub_files", lambda repo: [
        {"url": "https://h/a.safetensors", "size": 1}, {"url": "https://h/b.mlmodel", "size": 1}])
    monkeypatch.setattr("fichero_server.llm.model_downloads.fetch_file",
                        lambda url, dest, **kw: (dest.parent.mkdir(parents=True, exist_ok=True), dest.write_bytes(b"x")))
    with pytest.raises(RuntimeError, match="2 model files"):
        kr.download_recognition_model(READER)
    assert not kr.is_recognition_model_installed(READER)


def _hub(monkeypatch, body):
    import requests

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return body

    monkeypatch.setattr(requests, "get", lambda url, **kw: Response())


def test_the_hub_lists_the_one_model_file_pinned_to_the_commit_it_answered_with(monkeypatch):
    _hub(monkeypatch, {"tags": ["kraken"], "library_name": "kraken", "sha": "a" * 40, "siblings": [
        {"rfilename": "README.md", "size": 9}, {"rfilename": "small.safetensors", "size": 7}]})
    assert kr.hub_files(REPO) == [{"url": f"https://huggingface.co/{REPO}/resolve/{'a' * 40}/small.safetensors",
                                   "size": 7, "revision": "a" * 40}]


def test_a_repository_that_is_not_kraken_or_holds_two_model_files_is_refused_before_anything_downloads(monkeypatch):
    _hub(monkeypatch, {"tags": ["transformers"], "library_name": "transformers", "siblings": []})
    with pytest.raises(ValueError, match="not a Kraken"):
        kr.hub_files(REPO)
    _hub(monkeypatch, {"tags": ["kraken"], "sha": "b" * 40, "siblings": [
        {"rfilename": "a.safetensors", "size": 1}, {"rfilename": "b.mlmodel", "size": 1}]})
    with pytest.raises(ValueError, match="2 model files"):
        kr.hub_files(REPO)
    _hub(monkeypatch, {"tags": ["kraken"], "sha": "b" * 40, "siblings": [{"rfilename": "README.md", "size": 1}]})
    with pytest.raises(ValueError, match="0 model files"):
        kr.hub_files(REPO)


def test_the_installed_record_keeps_the_commit_it_was_fetched_at(data_home, monkeypatch):
    import json

    monkeypatch.setattr(kr, "require_installed", lambda: None)
    monkeypatch.setattr(kr, "hub_files", lambda repo: [
        {"url": f"https://huggingface.co/{repo}/resolve/{'c' * 40}/small.safetensors", "size": 7, "revision": "c" * 40}])
    monkeypatch.setattr("fichero_server.llm.model_downloads.fetch_file",
                        lambda url, dest, **kw: (dest.parent.mkdir(parents=True, exist_ok=True), dest.write_bytes(b"x" * 7)))
    kr.download_recognition_model(READER)
    assert json.loads(kr._marker_path(READER).read_text())["revision"] == "c" * 40


def test_the_search_makes_a_kraken_card_that_runs_on_this_mac_and_downloads(monkeypatch):
    async def fake(**kw):
        return [LISTING] if kw.get("task") == "image-to-text" and not kw.get("search") else []

    monkeypatch.setattr("fichero_server.api.routes.ai.models._fetch_hf_models", fake)
    monkeypatch.setattr(kr, "is_recognition_model_installed", lambda model_id, home=None: False)
    found, _ = asyncio.run(discovery.search_hugging_face(frozenset({"ar"})))
    card = next(c for c in found if c.pin.get("kraken_hf") == REPO)
    assert card.runs_here and card.local and card.source == "hugging-face"
    assert "Kraken" in card.offered_because
    assert discovery.candidate_installed(card) is False
    assert discovery.candidate_download(card) == {
        "runtime": "kraken", "model": READER, "action": "model.download",
        "params": {"runtime": "kraken", "model": READER}}
    from fichero_server.llm.places import THIS_MAC

    assert discovery.candidate_place(card) == THIS_MAC


def test_an_installed_hub_reader_is_listed_with_the_installed_readers(data_home, monkeypatch):
    from fichero_server.llm import local_model_catalog

    monkeypatch.setattr(kr, "require_installed", lambda: None)
    model = kr.recognition_data_home() / READER / "small.safetensors"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"x" * 7)
    kr.recognition_model_dir().mkdir(parents=True, exist_ok=True)
    kr._marker_path(READER).write_text(f'{{"hf": "{REPO}", "model_path": "{model}", "bytes": 7}}', encoding="utf-8")
    monkeypatch.setattr(kr, "is_installed", lambda: True)
    assert READER in [e.model_id for e in local_model_catalog.kraken_catalog_entries()]
