"""`models.row.installed-means-it-loads` (#6733 item 6): the repository records discovery lists as Kraken readers are
the ones the download accepts; a record that is not one is refused in words that name the cause."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.llm import kraken_runtime
from fichero_server.recipes import discovery


def _record(**kw):
    base = dict(doi="10.5281/zenodo.10519596", concept_doi="", software_name="other", keywords=["kraken_pytorch"],
                model_type=["recognition"], summary="", description="", license="cc-by-4.0", script=[], language=[],
                metrics={}, distribution=[], publication_date=None)
    return SimpleNamespace(**{**base, **kw})


def test_a_record_discovery_lists_is_one_the_download_accepts():
    record = _record()
    assert discovery._row(record) is not None
    assert kraken_runtime.is_kraken_recognition_record(record)


def test_a_segmentation_record_is_neither_listed_nor_downloadable():
    record = _record(model_type=["segmentation"])
    assert discovery._row(record) is None
    assert not kraken_runtime.is_kraken_recognition_record(record)


def test_the_download_of_a_record_that_is_not_a_reader_says_so_in_words(monkeypatch):
    pytest.importorskip("htrmopo")  # ci.python-tiers: htrmopo comes with scripts/setup_venv.sh, not uv.lock; a Linux runner has none
    import htrmopo

    monkeypatch.setattr(htrmopo, "get_description", lambda doi: _record(model_type=["segmentation"]))
    with pytest.raises(ValueError, match="not a Kraken recognition model"):
        kraken_runtime.download_recognition_model("kraken-zenodo-10519596")
