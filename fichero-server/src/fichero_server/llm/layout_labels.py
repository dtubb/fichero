"""DocLayNet label -> SegmOnto zone and subtype (#6749, kraken-scripts-eval 5.3).

A mapping, not a classifier: DocLayNet cannot tell a drop capital or a stamp from a Picture, and has none of
DropCapitalZone, MusicZone, DamageZone, DigitizationArtefactZone, StampZone, SealZone or QuireMarksZone.
"""
from __future__ import annotations

#: label -> (zone, subtype or None)
DOCLAYNET_LABELS: dict[str, tuple[str, str | None]] = {
    "Text": ("MainZone", None),
    "List-item": ("MainZone", "list"),
    "Section-header": ("MainZone", "head"),
    "Title": ("MainZone", "head"),
    "Caption": ("MainZone", None),
    "Formula": ("GraphicZone", "Maths"),
    "Footnote": ("MarginTextZone", "note"),
    "Page-header": ("RunningTitleZone", None),
    "Page-footer": ("NumberingZone", None),
    "Picture": ("GraphicZone", None),
    "Table": ("TableZone", None),
}


def segmonto_zone(label: str) -> tuple[str, str | None]:
    """The SegmOnto zone and subtype of a DocLayNet label; a label that is not one raises KeyError."""
    return DOCLAYNET_LABELS[label]
