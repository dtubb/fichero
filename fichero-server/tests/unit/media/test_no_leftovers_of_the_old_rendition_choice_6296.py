"""#6296 deleted `vision_base.frame_true_rendition_path`, `READ_FROM_ROLES` and `_frame_true_background_removed_path` (they put a
rendition over a person's edit). Nothing may still name them: a docstring that does sends a reader to code that is gone."""
from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "fichero_server"
GONE = ("frame_true_rendition_path", "READ_FROM_ROLES", "_frame_true_background_removed_path")


def test_nothing_in_src_names_the_deleted_rendition_choice():
    named = [f"{path.relative_to(SRC)}: {word}" for path in SRC.rglob("*.py") for word in GONE if word in path.read_text(encoding="utf-8")]
    assert named == []


def test_the_perf_baseline_has_no_entry_for_the_test_file_that_was_deleted():
    baseline = (Path(__file__).resolve().parents[2] / "perf_baseline.json").read_text(encoding="utf-8")
    assert "test_apple_vision_rendition_preference" not in baseline


def test_every_public_page_image_method_has_a_caller_in_src():
    """`PageImage` is the one answer to 'the page's current image'; a method nothing calls is code to read for no reason."""
    from fichero_server.media.current_image import PageImage

    own = SRC / "media" / "current_image.py"
    others = "\n".join(p.read_text(encoding="utf-8") for p in SRC.rglob("*.py") if p != own)
    inside = own.read_text(encoding="utf-8")
    unused = [name for name, member in vars(PageImage).items()
              if not name.startswith("_") and (callable(member) or isinstance(member, property))
              and f".{name}" not in others and inside.count(f".{name}") == 0]
    assert unused == []
