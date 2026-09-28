"""An image and its layout file pair whatever the CASE of the name the file states (2026-09-28).

WHY: the Ajami ALTO files (real, Zenodo 20392539, CC-BY-4.0) state `<fileName>ELIT_WAN_00130_003r.JPG`
while the image beside them is `ELIT_WAN_00130_003r.jpg` -- exports keep the camera's case, and
macOS is case-blind, so a person sees one file. Matching the stated name case-sensitively left
the pair to the stem alone; a renamed layout file then paired with nothing and imported as a raw
XML document. If this regresses, a layout file whose stem differs from its image's stops pairing.

Two images differing only by case are both matches, so that is refused BY NAME, never a pick.
Image paths are only listed, never read, so they need not exist (a case-blind disk could not hold
both `a.jpg` and `A.JPG`).
"""

from __future__ import annotations

from pathlib import Path

from fichero_server.importers.interchange_pairing import plan_pairs

AJAMI = Path(__file__).resolve().parents[1] / "formats" / "fixtures" / "corpus" / "ajami_fulfulde_elit-wan-00130-001r.alto.xml"
STATED = "ELIT_WAN_00130_001r.JPG"


def _layout(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(AJAMI.read_bytes())
    return path


def test_the_fixture_states_an_upper_case_name():
    assert f"<fileName>{STATED}</fileName>" in AJAMI.read_text(encoding="utf-8")


def test_a_renamed_layout_file_pairs_by_its_stated_name_in_another_case(tmp_path):
    layout = _layout(tmp_path, "transcription-page-1.xml")      # the stem names nothing
    image = tmp_path / "elit_wan_00130_001r.jpg"

    plan = plan_pairs([image, tmp_path / "other.jpg", layout])

    assert plan.pairs == {layout: image}, plan.unpaired


def test_the_stem_pairs_in_another_case(tmp_path):
    layout = _layout(tmp_path, "Folio-7.xml")
    # The stated name matches nothing here, so the stem decides.
    image = tmp_path / "folio-7.JPG"

    plan = plan_pairs([image, layout])

    assert plan.pairs == {layout: image}, plan.unpaired


def test_two_images_differing_only_by_case_are_refused_by_name(tmp_path):
    layout = _layout(tmp_path, "transcription-page-1.xml")
    lower, upper = tmp_path / "ELIT_WAN_00130_001r.jpg", tmp_path / "ELIT_WAN_00130_001r.JPG"

    plan = plan_pairs([lower, upper, layout])

    assert plan.pairs == {}
    assert "but for case" in plan.unpaired[layout] and upper.name in plan.unpaired[layout]
