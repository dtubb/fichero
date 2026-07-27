from PIL import Image

from pathlib import Path

import pytest
from fichero.llm import LLMConfig
from fichero.workflows.tools.zoom import zoom, zoom_image_file


def test_zoom_writes_upscaled_region_and_tiles(tmp_path):
    source = tmp_path / "page.png"
    Image.new("RGB", (100, 200)).save(source)

    region = zoom_image_file(source, tmp_path / "region", mode="region", x=10, y=20, width=30, height=40, output_format="png")
    tiles = zoom_image_file(source, tmp_path / "tiles", mode="tile", rows=2, output_format="png")

    assert region["error"] is None and len(region["outputs"]) == 1
    assert tiles["error"] is None and len(tiles["outputs"]) == 2
    with Image.open(region["outputs"][0]) as output:
        assert output.size == (60, 80)


@pytest.mark.asyncio
async def test_zoom_renders_selected_paleography_pdf_page(tmp_path):
    fixture = (
        Path(__file__).resolve().parents[2]
        / "fixtures/paleography/dialogo_lengua_page_18.pdf"
    )

    result = await zoom(
        {
            "files": [str(fixture)],
            "documents": [{"id": "page-18", "sequence": 1}],
            "mode": "tile",
            "rows": 2,
            "output_dir": str(tmp_path),
            "output_format": "png",
        },
        {},
        LLMConfig(provider="test", model="test"),
    )

    assert result["error"] is None
    assert len(result["files"]) == 2
    assert result["documents"] == [
        {"id": "page-18", "sequence": 1},
        {"id": "page-18", "sequence": 1},
    ]
    assert ".page-001.tile-01.png" in result["files"][0]
    with Image.open(result["files"][0]) as output:
        assert output.width > 500
        assert output.height > 500
