"""Reader cards a person can judge (#5617, MCP operator review 2026-10-08; `source/models-chains-and-projects.md`).

Why it matters: a Kraken reader downloaded from the repository was listed as "Kraken reader 10.5281/zenodo.…"
with "Downloaded from Kraken's model repository" and size 0; McCATMuS and CATMuS said size 0; a trained reader
whose file was 7 bytes was listed as usable. Every test goes through the routes (`GET /api/local-models`,
`GET /api/recipes/candidates`); the repository listing is the one discovery keeps, written here, never fetched.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DOI = "10.5281/zenodo.7933402"
RECORD = {
    "doi": DOI, "concept_doi": "10.5281/zenodo.6891851",
    "summary": "Fraktur model trained from enhanced Austrian Newspapers dataset",
    "description": "Recognition model for 19th century German Fraktur texts, printed newspapers",
    "licence": "CC-BY-SA-4.0", "scripts": ["Latn"], "languages": ["deu"], "keywords": ["Fraktur", "kraken_pytorch"],
    "cer_percent": 0.75, "size_bytes": 16_265_528, "published": "2026-03-23T12:13:26+00:00",
}


@pytest.fixture
def here(tmp_path, monkeypatch):
    """A model store and Kraken data folder of the test's own, with Kraken's repository listing kept."""
    store = tmp_path / "store"
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(store))
    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken-data"))
    (store / "discovery").mkdir(parents=True)
    (store / "discovery" / "kraken-repository.json").write_text(json.dumps(
        {"fetched_at": "2026-10-08T00:00:00+00:00", "records": [RECORD]}))
    markers = tmp_path / "kraken-data" / "recognition"
    markers.mkdir(parents=True)
    return markers


def _install(markers: Path, model_id: str, size: int) -> Path:
    weights = markers.parent / "htr-data" / model_id / "model.mlmodel"
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"w" * size)
    (markers / f"{model_id}.installed").write_text(json.dumps({"model_path": str(weights)}))
    return weights


def _kraken(client) -> dict[str, dict]:
    rows = client.get("/api/local-models", params={"model_type": "kraken"}).json()["models"]
    return {m["model_id"]: m for m in rows}


# -- source.find.repository-reader-named ----------------------------------------------------------------------


def test_source_find_repository_reader_named(client, here):
    """source.find.repository-reader-named: "named by its record's title, never only by its DOI, and its note says
    what the record states: its languages and scripts by name, the material ... and the period its words name, then
    where it came from (the DOI). Its size is the record's, else its downloaded file's, never 0 ... with no listing
    kept, it is named by its DOI ... A repository candidate's reason carries the same words.\""""
    _install(here, "kraken-zenodo-7933402", 4096)
    _install(here, "kraken-zenodo-1111", 2048)  # a reader whose record the kept listing does not hold

    rows = _kraken(client)
    reader = rows["kraken-zenodo-7933402"]
    assert reader["display_name"] == RECORD["summary"]
    for words in ("German", "Latin script", "print", "19th century", DOI):
        assert words in reader["note"], (words, reader["note"])
    assert reader["expected_size_mb"] == 16 and reader["size_bytes"] == 4096
    assert reader["metadata"]["license"] == "CC-BY-SA-4.0"

    unread = rows["kraken-zenodo-1111"]
    assert unread["display_name"] == "Kraken reader 10.5281/zenodo.1111"
    assert "has not been read" in unread["note"]
    assert unread["size_bytes"] == 2048 and unread["expected_size_mb"] == 0  # 2 KB rounds to 0 MB; bytes are there

    items = client.get("/api/recipes/candidates", params={"scripts": "Latn", "languages": "de",
                                                          "mac_memory_gb": 32}).json()["items"]
    card = next(c for c in items if c["source"] == "kraken-repository")
    assert card["name"] == RECORD["summary"] and card["size_gb"] == pytest.approx(0.0163)
    assert "German, Latin script, print, 19th century" in card["offered_because"], card["offered_because"]


# -- source.find.reader-size-real -----------------------------------------------------------------------------


def test_source_find_reader_size_real(client, here):
    """source.find.reader-size-real: "an installed Kraken reader of the catalogue's shortlist (McCATMuS, CATMuS
    Medieval) lists its size on disk as its downloaded file's (`size_bytes`; its record's when the file cannot be
    read) and its download size as its record's (`expected_size_mb`), never 0.\""""
    _install(here, "kraken-mccatmus", 8192)
    (here / "kraken-catmus-medieval.installed").write_text("{}")  # a marker naming no file

    rows = _kraken(client)
    assert rows["kraken-mccatmus"]["size_bytes"] == 8192
    assert rows["kraken-mccatmus"]["expected_size_mb"] == 16
    assert rows["kraken-catmus-medieval"]["size_bytes"] == 16_332_989
    assert rows["kraken-catmus-medieval"]["expected_size_mb"] == 16
