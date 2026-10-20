"""One key for one line of one page picture (`source.compare.pick-is-a-training-line`, #5900).

The same line can reach a training set twice: a person chose or typed its reading, and a bake-off staged a model's
reading of it. Both carry this key (the SHA-256 of the page image's bytes and the line's polygon rounded to whole
pixels), so a line in both is counted once, as the person's.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def image_digest(path: str | Path) -> str:
    """The SHA-256 of a page picture's bytes: the page, whatever it is called or where it lives."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def line_key(image_sha256: str, polygon_px: list) -> str:
    """The key of one line: its page picture's digest and its polygon in whole pixels."""
    points = ";".join(f"{round(x)},{round(y)}" for x, y in polygon_px)
    return hashlib.sha256(f"{image_sha256}|{points}".encode()).hexdigest()
