"""An unreadable source is refused by name — on the cloud path too.

Four checks — exists, readable, iCloud-dataless, cloud-placeholder — guarded
the Apple Vision path and ONLY the Apple Vision path. So the free, local,
on-device route refused an unavailable file honestly, and the paid cloud route,
which reaches the very same files, had none of them and went straight to
`Image.open()`.

That is precisely backwards, and it explains a beta report that arrived as two
separate complaints: "Showing thumbnail — original unavailable", and a
transcription that took forty-five minutes. A dataless iCloud file does not
raise when opened. It BLOCKS while macOS fetches it over the network — no
timeout, no progress, no message, and until recently on the event loop. An
unbounded silent download is a hang wearing a read's clothes.

It is the same lesson as the import stall fixed the night before
(`4ce243dbc` — "exists() is not readability"), on a path that had not learned
it.

These tests fake `os.stat` rather than manufacturing an iCloud file, because a
dataless file cannot be created on demand — and a test that silently skipped
when it could not make one would be worse than no test.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from fichero_server.workflows.tools import vision_base


def _stat(*, blocks: int = 8, size: int = 4096, flags: int = 0) -> SimpleNamespace:
    return SimpleNamespace(st_flags=flags, st_blocks=blocks, st_size=size)


def _fake_stat_for(monkeypatch, target, result):
    """Fake os.stat for ONE path and delegate every other path to the real one.

    Patching os.stat wholesale broke pytest itself: it stats its own files
    while filtering a traceback, got a SimpleNamespace with no st_mode, and
    died with an INTERNALERROR. A stdlib global has every caller in the process
    as its audience, not just the code under test.
    """
    real_stat = os.stat
    target = str(target)

    def stat(path, *args, **kwargs):
        if str(path) == target:
            return result
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", stat)


def test_a_readable_file_passes(tmp_path) -> None:
    real = tmp_path / "page.jpg"
    real.write_bytes(b"not really a jpeg, but it is readable")

    vision_base.assert_source_readable(str(real))  # must not raise


def test_a_missing_file_is_named(tmp_path) -> None:
    with pytest.raises(ValueError, match="File not found"):
        vision_base.assert_source_readable(str(tmp_path / "gone.jpg"))


def test_an_unreadable_file_is_named(tmp_path, monkeypatch) -> None:
    real = tmp_path / "locked.jpg"
    real.write_bytes(b"x")
    monkeypatch.setattr(os, "access", lambda _p, _mode: False)

    with pytest.raises(ValueError, match="File not readable"):
        vision_base.assert_source_readable(str(real))


def test_an_icloud_dataless_file_is_refused_not_downloaded(tmp_path, monkeypatch) -> None:
    """The one that mattered: refuse, never trigger a silent materialization."""
    real = tmp_path / "cloud.pdf"
    real.write_bytes(b"x")
    _fake_stat_for(monkeypatch, real, _stat(flags=0x40000000))

    with pytest.raises(ValueError, match="stored in iCloud and not downloaded"):
        vision_base.assert_source_readable(str(real))


def test_a_cloud_placeholder_is_refused(tmp_path, monkeypatch) -> None:
    """Zero blocks with a nonzero size is a stub standing in for real bytes."""
    real = tmp_path / "stub.pdf"
    real.write_bytes(b"x")
    _fake_stat_for(monkeypatch, real, _stat(blocks=0, size=999_999))

    with pytest.raises(ValueError, match="cloud placeholder"):
        vision_base.assert_source_readable(str(real))


def test_an_unstattable_path_is_reported_as_missing_not_as_a_cloud_verdict(
    tmp_path, monkeypatch
) -> None:
    """A stat failure must not be dressed up as an iCloud diagnosis.

    I wrote this expecting "does not raise" — the guard's own `except OSError`
    returns early rather than guessing. It raises anyway, and the reason is
    worth keeping: `os.path.exists()` is itself implemented with `os.stat`, so
    a path that cannot be stat'd fails the FIRST check and is reported as "File
    not found" before the cloud checks are ever reached.

    That is the honest outcome, so the test now says so instead of asserting my
    original intention. Operationally a file the filesystem will not describe is
    a file we do not have, and "File not found" names that without claiming to
    know it is an iCloud placeholder — which is the verdict that would have been
    invented. The early return in the guard still matters for the case it was
    written for: a stat that SUCCEEDS but lacks st_flags, on a filesystem that
    does not carry them.
    """
    real = tmp_path / "odd.jpg"
    real.write_bytes(b"x")

    real_stat = os.stat

    def boom(path, *args, **kwargs):
        if str(path) == str(real):
            raise OSError("filesystem said no")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", boom)

    with pytest.raises(ValueError, match="File not found") as caught:
        vision_base.assert_source_readable(str(real))

    message = str(caught.value)
    assert "iCloud" not in message and "placeholder" not in message


# --- the point of the whole exercise: the CLOUD seams check too -------------


def test_file_to_data_uri_refuses_a_dataless_source(tmp_path, monkeypatch) -> None:
    """The paid path must refuse what the free path already refused."""
    real = tmp_path / "cloud.jpg"
    real.write_bytes(b"x")
    _fake_stat_for(monkeypatch, real, _stat(flags=0x40000000))

    with pytest.raises(ValueError, match="stored in iCloud"):
        vision_base.file_to_data_uri(str(real))


def test_pdf_page_render_refuses_a_dataless_source(tmp_path, monkeypatch) -> None:
    """Same for the PDF render — the path the 45-minute report came from."""
    real = tmp_path / "cloud.pdf"
    real.write_bytes(b"x")
    _fake_stat_for(monkeypatch, real, _stat(blocks=0, size=1_200_000))

    with pytest.raises(ValueError, match="cloud placeholder"):
        vision_base._pdf_page_to_data_uri(str(real), page_index=0)


def test_the_refusal_names_the_file(tmp_path, monkeypatch) -> None:
    """A user cannot act on 'a file was unavailable'."""
    real = tmp_path / "Mis padecimientos.pdf"
    real.write_bytes(b"x")
    _fake_stat_for(monkeypatch, real, _stat(flags=0x40000000))

    with pytest.raises(ValueError) as caught:
        vision_base.assert_source_readable(str(real))

    assert "Mis padecimientos.pdf" in str(caught.value)
