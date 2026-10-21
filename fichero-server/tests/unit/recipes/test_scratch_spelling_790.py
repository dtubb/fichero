"""## 790 LOW (#5368): a try's scratch copy is mapped to its real project by the engine's own folder key."""
from __future__ import annotations

from pathlib import Path

from fichero_server.recipes import places


def test_a_scratch_copy_spelled_another_way_still_finds_its_project(tmp_path):
    """## 790 LOW: the mapping is keyed like the engine's open libraries (NFC + realpath), so `/var/…` and `/private/var/…` agree."""
    real = tmp_path / "real.fichero"
    scratch = tmp_path / "try.fichero"
    real.mkdir()
    scratch.mkdir()
    other_spelling = Path(str(scratch).replace("/private/var", "/var", 1))
    with places.scratch_of(scratch, real):
        with places.bound_project(other_spelling):
            assert places.bound_library() == real
