"""HTR-United's catalogue is searched for ground truth by the project's languages and scripts (#5571,
`source.find.htr-united-and-tessdata`): a dataset's licence, size and format are shown with it, none is ever the
rules' choice, and the network is only touched behind the egress check. The listing is a recorded part of the real
catalogue (`catalog.json` of github.com/HTR-United/htr-united, 2026-10-18)."""
import json
from pathlib import Path

from fichero_server.recipes import htr_united

CATALOG = json.loads((Path(__file__).parent / "data" / "htr_united_catalog.json").read_text())


def _rows():
    return htr_united.rows(CATALOG)


def test_each_dataset_keeps_what_a_person_needs_to_judge_it():
    row = next(r for r in _rows() if r["title"].startswith("AMSMB"))
    assert row["languages"] == ["la", "ca"]  # ISO 639-3 in the catalogue, the tags setup stores here
    assert row["format"] == "Page-XML" and row["lines"] and row["licence"]["name"]
    assert row["url"] and row["handwriting"] is True


def test_a_licence_given_as_a_list_is_read_as_its_first_entry():
    assert all(isinstance(r["licence"], dict) for r in _rows())


def test_datasets_are_found_by_the_projects_language_and_script_most_lines_first():
    found = htr_united.matching(_rows(), languages=frozenset({"la"}), scripts=frozenset({"Latn"}))
    assert found and all("la" in r["languages"] for r in found)
    assert [r["lines"] or 0 for r in found] == sorted((r["lines"] or 0 for r in found), reverse=True)


def test_handwriting_is_asked_apart_from_print():
    typed = htr_united.matching(_rows(), languages=frozenset({"hi"}), scripts=frozenset(), handwriting=False)
    assert typed and all(not r["handwriting"] for r in typed)
    assert htr_united.matching(_rows(), languages=frozenset({"hi"}), scripts=frozenset(), handwriting=True) == []


def test_a_language_no_dataset_has_finds_nothing():
    assert htr_united.matching(_rows(), languages=frozenset({"zu"}), scripts=frozenset()) == []


def test_the_listing_is_kept_and_read_back_without_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(htr_united, "_store_root", lambda: tmp_path)
    monkeypatch.setattr(htr_united, "_harvest", lambda: CATALOG)
    kept = htr_united.refresh()
    assert kept["records"] == _rows()
    monkeypatch.setattr(htr_united, "_harvest", lambda: (_ for _ in ()).throw(AssertionError("network")))
    assert htr_united.cached()["records"] == _rows()


def test_nothing_kept_reads_as_none(tmp_path, monkeypatch):
    monkeypatch.setattr(htr_united, "_store_root", lambda: tmp_path)
    assert htr_united.cached() is None


def _answers():
    from fichero_server.recipes.assemble import Answers

    return Answers(purposes=("transcribe",), languages=frozenset({"la"}), scripts=frozenset({"Latn"}),
                   materials=("handwriting",), mac_memory_gb=16)


def test_the_finder_counts_the_kept_datasets_for_the_projects_languages(tmp_path, monkeypatch):
    from fichero_server.recipes import discovery

    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    monkeypatch.setattr(htr_united, "_harvest", lambda: CATALOG)
    htr_united.refresh()
    _cards, sources = discovery.discover(_answers(), online=False)
    source = {s["source"]: s for s in sources}["htr-united"]
    assert source["state"] == "cached" and source["count"] == len(
        htr_united.matching(_rows(), languages=frozenset({"la"}), scripts=frozenset({"Latn"})))
    assert "HTR-United" in source["detail"] and len(source["detail"]) <= 48


def test_an_online_search_fetches_the_catalogue_when_none_is_kept(tmp_path, monkeypatch):
    from fichero_server.recipes import discovery

    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    monkeypatch.setattr(discovery, "egress_allowed", lambda: True)
    monkeypatch.setattr(discovery, "refresh_repository", lambda: {"records": []})
    monkeypatch.setattr(discovery, "search_hugging_face", _no_hub)
    monkeypatch.setattr(htr_united, "_harvest", lambda: CATALOG)
    result = discovery.search_online(frozenset({"la"}))
    assert result["sources"]["htr-united"]["state"] == "searched"
    assert htr_united.cached() is not None


async def _no_hub(*_a, **_k):
    return [], []


import pytest  # noqa: E402


@pytest.mark.parametrize("bad", [[], "html", {"1": "x"}, {"1": {"language": "lat"}}, {"1": {"volume": 5}}])
def test_a_malformed_catalogue_is_a_value_error_the_finder_survives(bad, tmp_path, monkeypatch):
    from fichero_server.recipes import discovery

    with pytest.raises(ValueError):
        htr_united.rows(bad)
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    monkeypatch.setattr(discovery, "egress_allowed", lambda: True)
    monkeypatch.setattr(discovery, "refresh_repository", lambda: {"records": []})
    monkeypatch.setattr(discovery, "search_hugging_face", _no_hub)
    monkeypatch.setattr(htr_united, "_harvest", lambda: bad)
    assert discovery.search_online(frozenset({"la"}))["sources"]["htr-united"]["state"] == "failed"


def test_an_open_dataset_is_offered_as_a_test_set_and_as_training_data():
    (offer,) = htr_united.offered([{**_rows()[0], "licence": {"name": "CC-BY-4.0", "url": "u"}, "format": "Page-XML"}])
    assert offer["as"] == ["test-set", "training"] and offer["accept"] is None and offer["importable"] is True


def test_a_licence_that_needs_accepting_is_offered_only_with_the_words_to_accept_it():
    (offer,) = htr_united.offered([{**_rows()[0], "licence": {"name": "CC-BY-NC-4.0", "url": "u"}}])
    assert offer["as"] == [] and "CC-BY-NC-4.0" in offer["accept"]  # nothing is used before it is accepted


def test_an_unstated_licence_is_never_used_unaccepted():
    (offer,) = htr_united.offered([{**_rows()[0], "licence": {"name": "", "url": ""}}])
    assert offer["as"] == [] and "not stated" in offer["accept"]


def test_a_dataset_in_a_format_fichero_cannot_import_says_so():
    (offer,) = htr_united.offered([{**_rows()[0], "licence": {"name": "CC0-1.0", "url": ""}, "format": "TEI"}])
    assert offer["importable"] is False


def test_the_offers_route_lists_what_the_kept_catalogue_has_for_the_projects_languages(client, monkeypatch):
    monkeypatch.setattr(htr_united, "cached", lambda: {"fetched_at": "x", "records": _rows()})
    r = client.get("/api/recipes/htr-united", params={"languages": "la", "scripts": "Latn"})
    assert r.status_code == 200 and r.json()["datasets"] and all("as" in d for d in r.json()["datasets"])


def test_a_licence_with_no_url_or_name_is_kept_whole_and_the_route_model_takes_it():
    from fichero_server.api.routes.system.recipes import HtrUnitedLicence

    entry = {"title": "t", "license": {"name": "CC0-1.0"}}
    (row,) = htr_united.rows({"a": entry})
    assert row["licence"] == {"name": "CC0-1.0", "url": ""}
    (row,) = htr_united.rows({"a": {"title": "t", "license": {}}})
    assert HtrUnitedLicence(**row["licence"]).name == ""
