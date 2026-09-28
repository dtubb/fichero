"""A layout file names its image in whatever case it was first recorded; the Mac ignores case (#5220).

The Ajami ALTO in the maintainer's test corpus states `<fileName>ELIT_WAN_00130_003r.JPG</fileName>`
while the file on disk is `ELIT_WAN_00130_003r.jpg`. A stem fallback happened to rescue that
folder, but a layout whose stem differs from its image (`p3.xml` naming `SCAN_0003.JPG`) had only
the stated name to go on, and a case-sensitive comparison left it unpaired -- its layout imported
as a raw text document. Two images differing only by case must be reported, never guessed.
"""

from __future__ import annotations

from pathlib import Path

from fichero_server.importers.interchange_pairing import _match

FOLDER = Path("/corpus/register")


def test_a_stated_name_in_another_case_still_finds_its_image():
    image = FOLDER / "scan_0003.jpg"
    match = _match(FOLDER / "p3.xml", "SCAN_0003.JPG", {FOLDER: [image, FOLDER / "scan_0004.jpg"]})
    assert match == image, match


def test_images_differing_only_by_case_are_reported_not_guessed():
    images = [FOLDER / "Scan_0003.jpg", FOLDER / "scan_0003.JPG"]
    match = _match(FOLDER / "p3.xml", "SCAN_0003.jpg", {FOLDER: images})
    assert isinstance(match, str) and "but for case" in match, match


def test_an_exact_stated_name_still_wins():
    image = FOLDER / "f_12r.tif"
    assert _match(FOLDER / "other.xml", "f_12r.tif", {FOLDER: [image, FOLDER / "f_12v.tif"]}) == image
