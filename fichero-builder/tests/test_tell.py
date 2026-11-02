"""`builder tell` (manager 2026-11-02: tell.sh was untracked, and a long message arrived as its last line only)."""
from __future__ import annotations

import os

from fichero_builder import __main__ as cli
from fichero_builder import journal, tell


def test_a_short_message_is_typed_and_a_long_one_goes_to_a_file_the_pane_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    b = tmp_path / "bin"
    b.mkdir()
    log = tmp_path / "keys"
    (b / "tmux").write_text(f'#!/bin/sh\ncase "$1" in list-panes) echo "%9";; capture-pane) echo "❯ ";; send-keys) shift; echo "$@" >> {log};; esac\n')
    (b / "tmux").chmod(0o755)
    monkeypatch.setenv("PATH", f"{b}:{os.environ['PATH']}")
    monkeypatch.setattr(tell.time, "sleep", lambda s: None)
    assert cli.main(["tell", "%9", "LANDED", "abc123"]) == 0
    assert "-l LANDED abc123" in log.read_text()
    long = "x" * 500
    assert tell.send("%9", long, sleep=lambda s: None)[0] == 0
    (f,) = (tmp_path / "s" / "tells").iterdir()
    assert f.read_text().strip() == long and f"-l Read {f}" in log.read_text()
    assert tell.send("%404", "hi")[0] == 1, "no such pane"
