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


def test_denoise_replays_deterministically():
    image = Image.new("RGB", (9, 9), "white")
    image.putpixel((4, 4), (0, 0, 0))
    operation = {"op": "denoise", "params": {"radius": 3}}
    assert apply_operation(image, operation).tobytes() == apply_operation(image, operation).tobytes()
