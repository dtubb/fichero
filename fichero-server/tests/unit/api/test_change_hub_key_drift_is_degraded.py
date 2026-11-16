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
    """engine.silent.change-hub-key-drift: an emit path that came off the filesystem in NFD reaches a window subscribed in NFC."""
    name = "Proyecto Mosquera Ñ.fichero"
    pkg = tmp_path / unicodedata.normalize("NFC", name)
    pkg.mkdir()
    nfd = str(tmp_path / unicodedata.normalize("NFD", name))
    queue = hub.subscribe(str(pkg))
    delivered = hub.emit(nfd, ChangeEvent(type="segment.updated"))
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


def _drift_lines(caplog, level):
    return [r for r in caplog.records if "reached 0 subscribers" in r.getMessage() and r.levelno >= level]


def test_same_library_under_another_spelling_warns_once_per_pair_with_a_count(hub, tmp_path, caplog):
    hub.subscribe(str(tmp_path / "PROJECT.fichero"))
    with caplog.at_level(logging.DEBUG, logger="fichero_server.api.change_stream"):
        for _ in range(25):
            hub.emit(str(tmp_path / "Project.fichero"), ChangeEvent(type="segment.updated"))
    lines = _drift_lines(caplog, logging.WARNING)
    assert len(lines) == 2  # the 1st emit and the 10th, not 25
    assert "10 emit(s) dropped" in lines[1].getMessage()


def test_a_different_library_with_no_window_does_not_warn(hub, tmp_path, caplog):
    """A base library and its numbered copy are two libraries; emitting to the one nobody has open is normal."""
    hub.subscribe(str(tmp_path / "Project 12.fichero"))
    with caplog.at_level(logging.DEBUG, logger="fichero_server.api.change_stream"):
        for _ in range(25):
            hub.emit(str(tmp_path / "Project.fichero"), ChangeEvent(type="segment.updated"))
    assert _drift_lines(caplog, logging.WARNING) == []
    assert len(_drift_lines(caplog, logging.DEBUG)) == 2


def test_the_throttle_memory_is_bounded(tmp_path):
    from fichero_server.api import change_stream as cs

    hub = _ChangeHub()
    hub.subscribe(str(tmp_path / "Open.fichero"))
    for i in range(cs._DRIFT_PAIR_CAP + 50):
        hub.emit(str(tmp_path / f"Lib {i}.fichero"), ChangeEvent(type="segment.updated"))
    assert len(hub._drift_counts) == cs._DRIFT_PAIR_CAP


def test_unsubscribe_and_count_use_the_canonical_key(hub, tmp_path):
    real = tmp_path / "Project.fichero"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(tmp_path)
    queue = hub.subscribe(str(link / "Project.fichero"))
    assert hub.subscriber_count(str(real)) == 1
    hub.unsubscribe(str(real), queue)
    assert hub.subscriber_count(str(link / "Project.fichero")) == 0
