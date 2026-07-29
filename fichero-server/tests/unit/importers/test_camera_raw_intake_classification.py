"""#2354: DSLR/external-camera (RAW) files are recognized by watched-folder intake.

A watched folder where camera software / SD-card import drops files must
identify camera images. If the ingest classifier doesn't map a RAW extension to
FileType.image, that file lands as FileType.other and is silently mishandled
(no image pipeline, no thumbnail/OCR). Pin the classification + keep the ingest
classifier and the image loader's RAW support from drifting apart.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.importers.ingest import detect_file_type
from fichero_server.loaders.image_loader import RAW_FORMATS
from fichero_server.models import FileType

# Common DSLR/mirrorless RAW extensions an import directory will see.
_DSLR_FORMATS = [".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2"]


@pytest.mark.parametrize("ext", _DSLR_FORMATS)
def test_dslr_raw_is_classified_as_image(ext):
    assert detect_file_type(Path(f"/camera/IMG_0001{ext}")) == FileType.image, (
        f"{ext} must be intake-classified as an image, not silently FileType.other"
    )


@pytest.mark.parametrize("ext", sorted(RAW_FORMATS))
def test_loader_raw_formats_are_ingest_images(ext):
    """No drift: every RAW format the image loader supports must be an image to
    the ingest classifier (else the watched folder skips/mishandles it)."""
    assert detect_file_type(Path(f"/camera/shot{ext}")) == FileType.image, (
        f"image_loader supports {ext} but ingest classifies it as "
        f"{detect_file_type(Path(f'/camera/shot{ext}'))} — fix _FILE_TYPE_MAP"
    )


def test_case_insensitive_extension():
    # Camera software often writes uppercase extensions (IMG_0001.CR2).
    assert detect_file_type(Path("/camera/IMG_0002.CR2")) == FileType.image


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
