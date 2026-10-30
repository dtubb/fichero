"""#6296 deleted `vision_base.frame_true_rendition_path`, `READ_FROM_ROLES` and `_frame_true_background_removed_path` (they put a
rendition over a person's edit). Nothing may still name them: a docstring that does sends a reader to code that is gone."""
from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "fichero_server"
GONE = ("frame_true_rendition_path", "READ_FROM_ROLES", "_frame_true_background_removed_path")


def test_nothing_in_src_names_the_deleted_rendition_choice():
    named = [f"{path.relative_to(SRC)}: {word}" for path in SRC.rglob("*.py") for word in GONE if word in path.read_text(encoding="utf-8")]
    assert named == []
