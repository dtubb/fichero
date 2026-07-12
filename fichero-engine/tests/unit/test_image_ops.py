from PIL import Image

from fichero.image_ops import apply_operation


def test_rotate_and_straighten_use_bicubic_white_fill(monkeypatch):
    seen = []
    original = Image.Image.rotate

    def rotate(self, *args, **kwargs):
        seen.append(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "rotate", rotate)
    image = Image.new("RGB", (10, 10), "black")
    for operation in ("rotate", "straighten"):
        apply_operation(image, {"op": operation, "params": {"angle": 3}})
    assert all(item["resample"] == Image.Resampling.BICUBIC and item["fillcolor"] == "white" for item in seen)
