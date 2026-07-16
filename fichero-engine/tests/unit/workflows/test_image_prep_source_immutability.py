"""Every image-prep tool must leave its input bytes untouched (#3908)."""

import asyncio
import hashlib
from pathlib import Path

from PIL import Image

from fichero.db import db_manager
from fichero.llm import LLMConfig
from fichero.models import Document, FileType
from fichero.workflows.tools.auto_crop_border_images import auto_crop_border_images
from fichero.workflows.tools.enhance_images import enhance_image_file
from fichero.workflows.tools.fuzzy_clean_images import fuzzy_clean_image_file
from fichero.workflows.tools.prepare_images import prepare_image_file
from fichero.workflows.tools.remove_background_images import remove_background_image_file
from fichero.workflows.tools.rotate_images import rotate_image_file
from fichero.workflows.tools.segment_images import segment_image_file
from fichero.workflows.tools.split_images import split_image_file
from fichero.workflows.tools.zoom import zoom_image_file


def _fixture_image(path):
    image = Image.new("RGB", (100, 100), "white")
    for x in range(20, 80):
        for y in range(20, 80):
            image.putpixel((x, y), (0, 0, 0))
    image.save(path)


def test_image_prep_helpers_write_derivatives_without_mutating_source(tmp_path):
    source = tmp_path / "scan.png"
    _fixture_image(source)
    helpers = {
        "enhance_images": lambda output: enhance_image_file(source, output, output_format="png"),
        "prepare_images": lambda output: prepare_image_file(source, output, output_format="png"),
        "segment_images": lambda output: segment_image_file(source, output, output_format="png"),
        "split_images": lambda output: split_image_file(source, output, output_format="png"),
        "rotate_images": lambda output: rotate_image_file(source, output, output_format="png"),
        "remove_background_images": lambda output: remove_background_image_file(source, output, output_format="png"),
        "fuzzy_clean_images": lambda output: fuzzy_clean_image_file(source, output, output_format="png"),
        "zoom": lambda output: zoom_image_file(source, output, mode="tile", rows=2, output_format="png"),
    }

    for name, helper in helpers.items():
        before = hashlib.sha256(source.read_bytes()).digest()
        result = helper(tmp_path / name)
        assert result["error"] is None, (name, result)
        assert result["outputs"] and all(path for path in result["outputs"])
        assert all(Path(path).is_file() for path in result["outputs"])
        assert hashlib.sha256(source.read_bytes()).digest() == before, name


def test_auto_crop_border_records_a_reversible_derivative_without_mutating_source(tmp_path):
    source = tmp_path / "scan.png"
    _fixture_image(source)
    before = hashlib.sha256(source.read_bytes()).digest()
    library_path = tmp_path / "Library.fichero"
    db = db_manager.get_database(library_path)
    document = Document(name=source.name, path=str(source), file_type=FileType.image)
    db.save(document)

    result = asyncio.run(
        auto_crop_border_images(
            {"documents": [document.model_dump(mode="json")]},
            {"library_path": str(library_path)},
            LLMConfig(provider="test", model="test"),
        )
    )

    assert result["image_edit_operations"][0]["operation"]["op"] == "auto_crop_border"
    assert hashlib.sha256(source.read_bytes()).digest() == before
