"""#6814 `recipes-run.engine.not-sure-does-not-starve-the-import`: Set Up's "Not sure" quick read works on a reduced picture and
gives up on a page after a deadline, so a slow read says "could not tell" instead of holding the answer for minutes."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from PIL import Image

from fichero_server.recipes import language_guess


def _doc(tmp_path, size=(4000, 2680)):
    path = tmp_path / "p.jpg"
    Image.new("RGB", size, (230, 220, 200)).save(path)
    return SimpleNamespace(page_content="", path=str(path))


def _vision_here(monkeypatch, read):
    from fichero_server.training import evaluation
    from fichero_server.workflows.tools import vision_base

    monkeypatch.setattr(evaluation, "apple_vision_here", lambda: True)
    monkeypatch.setattr(vision_base, "apple_vision_ocr", read)


def test_the_quick_read_gets_a_reduced_picture(tmp_path, monkeypatch):
    seen = []

    def read(path, language):
        with Image.open(path) as picture:
            seen.append(picture.size)
        return "texto de la pagina"

    _vision_here(monkeypatch, read)
    assert language_guess._page_text(None, tmp_path, _doc(tmp_path)) == "texto de la pagina"
    assert seen and max(seen[0]) <= language_guess.QUICK_READ_PIXELS, f"read at {seen}"


def test_a_slow_read_gives_up_at_the_deadline_and_says_so(tmp_path, monkeypatch):
    release = threading.Event()
    _vision_here(monkeypatch, lambda path, language: release.wait(5) and "never used")
    monkeypatch.setattr(language_guess, "QUICK_READ_SECONDS", 0.3)
    started = time.monotonic()
    try:
        guess = language_guess._guess(None, tmp_path, [_doc(tmp_path)])
    finally:
        release.set()
    assert time.monotonic() - started < 2.0, "the guess waited for the slow read"
    assert guess["code"] is None and guess["sentence"].startswith("Could not tell the language")
