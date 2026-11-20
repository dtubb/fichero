"""The line finder's base model and network height for a script, as measured (#6752, kraken-scripts-eval 3.1, 3.2).

The height is the page height in network pixels: a text line should be 25-40 px tall there. Large-script
manuscripts (right-to-left, Devanagari) are found whole at 1200 and in pieces at 1800; Latin book pages need 1800.
A script not listed was not measured and keeps the bundled base at 1800. Which base a recipe step loads and how
the height reaches Kraken is the caller's; this table only says what was measured.
"""
from __future__ import annotations

from typing import NamedTuple


class SegmenterDefaults(NamedTuple):
    base: str  # "bundled" (kraken's own) or "2026" (10.5281/zenodo.22879549)
    height: int


DEFAULT = SegmenterDefaults("bundled", 1800)

_BY_SCRIPT: dict[str, SegmenterDefaults] = {
    "Hebr": SegmenterDefaults("2026", 1200),  # recall 0.62 -> 1.00
    "Arab": SegmenterDefaults("2026", 1200),  # Aljamiado 0.37 -> 0.81, Ajami 0.50 -> 0.91, Urdu 0.86 -> 0.95
    "Deva": SegmenterDefaults("2026", 1200),  # 0.65 -> 0.92
    "Aran": SegmenterDefaults("bundled", 1200),  # Persian nastaliq 0.98 bundled at 1200
    "Syrc": SegmenterDefaults("bundled", 1200),  # estrangela 0.99, serto 0.81; the 2026 base is worse
    "Syre": SegmenterDefaults("bundled", 1200),
    "Syrj": SegmenterDefaults("bundled", 1200),
    "Syrn": SegmenterDefaults("bundled", 1200),
    "Newa": SegmenterDefaults("bundled", 300),  # palm-leaf strips: nothing at 600 or above
}


def segmenter_defaults(script: str | None) -> SegmenterDefaults:
    """The measured base and height for an ISO 15924 script code; the default for none or an unmeasured one."""
    return _BY_SCRIPT.get(script or "", DEFAULT)
