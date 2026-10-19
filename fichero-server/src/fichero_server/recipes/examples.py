"""The credit of every borrowed example the app shows (#5803, `source.onboard.credits.link-source-and-licence`).

Each record names the item's own page and its licence's deed, so the app links both and hard-codes neither. The page,
its lines and what the stages make of them ship with the app (`Resources/StageShowcase/<id>.json`); a test keeps this
record equal to the credit fields in that file, so the two cannot drift.
"""

from __future__ import annotations

from typing import Any

#: The example page every stage's example is about (the one document: the picture, the fields and the sentence).
EXAMPLE_ID = "dialogo-lengua-p18"

EXAMPLE_RECORDS: dict[str, dict[str, Any]] = {
    EXAMPLE_ID: {
        "title": "Diálogo de la Lengua, manuscript p. 18",
        "short_credit": "Example: BNE · DILE, CC BY-SA 4.0",
        "licence": "Manuscript public domain (BNE Digital, reuse with the credit); transcription CC BY-SA 4.0",
        # The page of the transcription at DILE (the item's own page); the holding library's record is the BNE's.
        "source_url": "https://dile.dragoman.org/1/18.pdf",
        "licence_url": "https://creativecommons.org/licenses/by-sa/4.0/",
    },
}


def example_credit(example_id: str = EXAMPLE_ID) -> dict[str, Any]:
    """What the stage listing carries for an example: its credit line and both links."""
    return dict(EXAMPLE_RECORDS[example_id])
