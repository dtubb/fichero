from PIL import Image

from fichero.workflows.tools.zoom import zoom_image_file


def test_zoom_writes_upscaled_region_and_tiles(tmp_path):
    source = tmp_path / "page.png"
    Image.new("RGB", (100, 200)).save(source)

    region = zoom_image_file(source, tmp_path / "region", mode="region", x=10, y=20, width=30, height=40, output_format="png")
    tiles = zoom_image_file(source, tmp_path / "tiles", mode="tile", rows=2, output_format="png")

    assert region["error"] is None and len(region["outputs"]) == 1
    assert tiles["error"] is None and len(tiles["outputs"]) == 2
    with Image.open(region["outputs"][0]) as output:
        assert output.size == (60, 80)
