"""#6749: a DocLayNet label becomes a SegmOnto zone, with its subtype where SegmOnto has one (eval 5.3)."""
from __future__ import annotations

import pytest

from fichero_server.llm.layout_labels import DOCLAYNET_LABELS, segmonto_zone


@pytest.mark.parametrize("label, zone, subtype", [
    ("Text", "MainZone", None),
    ("List-item", "MainZone", "list"),
    ("Section-header", "MainZone", "head"),
    ("Title", "MainZone", "head"),
    ("Caption", "MainZone", None),
    ("Formula", "GraphicZone", "Maths"),
    ("Footnote", "MarginTextZone", "note"),
    ("Page-header", "RunningTitleZone", None),
    ("Page-footer", "NumberingZone", None),
    ("Picture", "GraphicZone", None),
    ("Table", "TableZone", None),
])
def test_each_doclaynet_label_has_its_segmonto_zone(label, zone, subtype):
    assert segmonto_zone(label) == (zone, subtype)


def test_all_eleven_labels_are_mapped_and_an_unknown_label_is_refused():
    assert len(DOCLAYNET_LABELS) == 11
    with pytest.raises(KeyError):
        segmonto_zone("MainZone")
