"""engine.silent.change-hub-key-drift (#6309): one spelling per library, one warning per drifting pair."""

from __future__ import annotations

import logging
import unicodedata

import pytest

from fichero_server.api.change_stream import ChangeEvent, _ChangeHub


@pytest.fixture
def hub():
    return _ChangeHub()


def test_accented_name_in_either_unicode_form_reaches_the_window(hub, tmp_path):
    """engine.silent.change-hub-key-drift: a window sends the NFD spelling macOS gives, the engine emits NFC."""
    name = "Proyecto Mosquera Ñ.fichero"
    pkg = tmp_path / unicodedata.normalize("NFC", name)
    pkg.mkdir()
    nfd = str(tmp_path / unicodedata.normalize("NFD", name))
    queue = hub.subscribe(nfd)
    delivered = hub.emit(str(pkg), ChangeEvent(type="segment.updated"))
    assert delivered == 1
    assert queue.qsize() == 1


def test_symlink_and_real_spelling_share_a_key(hub, tmp_path):
    real = tmp_path / "Project.fichero"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(tmp_path)
    queue = hub.subscribe(str(link / "Project.fichero"))
    assert hub.emit(str(real), ChangeEvent(type="document.updated")) == 1
    assert queue.qsize() == 1


def test_drift_warns_once_per_pair_with_a_count(hub, tmp_path, caplog):
    hub.subscribe(str(tmp_path / "Project 12.fichero"))
    with caplog.at_level(logging.WARNING, logger="fichero_server.api.change_stream"):
        for _ in range(25):
            hub.emit(str(tmp_path / "Project.fichero"), ChangeEvent(type="segment.updated"))
    lines = [r for r in caplog.records if "reached 0 subscribers" in r.getMessage()]
    assert len(lines) == 2  # the 1st emit and the 10th, not 25
    assert "10 emit(s) dropped" in lines[1].getMessage()
