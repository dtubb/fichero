"""Cross-cutting replay invariants for archival image operations (#3625)."""
from PIL import Image

from fichero.media.image_ops import apply_operation


OPS = [
    {"op": "denoise", "params": {"radius": 3}},
    {"op": "auto_deskew", "params": {"angle": 0}},
    {"op": "auto_crop_border", "params": {}},
    {"op": "adaptive_binarize", "params": {}},
]


def _source():
    image = Image.new("RGB", (20, 20), "black")
    for x in range(3, 17):
        for y in range(3, 17):
            image.putpixel((x, y), (180, 180, 180))
    return image


def _replay(operations):
    image = _source()
    for operation in operations:
        image = apply_operation(image, operation)
    return image


def test_archival_ops_replay_deterministically_and_removal_replays_from_source():
    assert _replay(OPS).tobytes() == _replay(OPS).tobytes()
    for index in range(len(OPS)):
        assert _replay(OPS[:index] + OPS[index + 1:]).tobytes() == _replay(OPS[:index] + OPS[index + 1:]).tobytes()


def test_archival_ops_reject_unknown_operation():
    from fastapi import HTTPException
    import pytest
    with pytest.raises(HTTPException):
        apply_operation(_source(), {"op": "not-an-op", "params": {}})
