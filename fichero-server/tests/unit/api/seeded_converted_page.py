"""A seeded, converted page: real boxes with Kraken-style polygons and baselines, real readings,
edited through the real routes. The probe fixture #5072's segment-level sweep never had.

`seed_page(db, ...)` builds a PDF parent + one page child + one `transcription` artifact (provider
openai / model gpt-4o, so a vision rerun with that LLMConfig MATCHES it), with `count` line boxes.
Each box carries `polygon_px`, `baseline_px`, `pixel_frame` (1000x1000) and a char span into the
artifact content. Nothing here edits anything; the probes do that through the routes/actions.
"""
from __future__ import annotations

from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document, FileType, Status

LINES = ["In the year of our Lord", "one thousand eight hundred", "and fifty two, the ship", "sailed from Cadiz"]
FRAME = {"width": 1000, "height": 1000}


def line_box(i: int, char_start: int, text: str) -> OCRGeometryBox:
    x, y, w, h = 0.10, 0.10 + i * 0.15, 0.60, 0.05
    px = lambda fx, fy: [round(fx * 1000), round(fy * 1000)]  # noqa: E731
    return OCRGeometryBox(
        text=text, bbox=[x, y, w, h], level="line", confidence=0.9,
        char_start=char_start, char_end=char_start + len(text),
        provider="openai", model="gpt-4o",
        metadata={
            "polygon_px": [px(x, y), px(x + w, y), px(x + w, y + h), px(x, y + h)],
            "baseline_px": [px(x, y + h * 0.8), px(x + w, y + h * 0.8)],
            "pixel_frame": dict(FRAME),
        },
    )


def seed_page(db, count: int = 4):
    """-> (parent, page, artifact)."""
    parent = Document(name="book.pdf", doc_type=DocType.file, file_type=FileType.pdf,
                      path="/path/book.pdf", status=Status.completed)
    db.save(parent)
    page = Document(name="book p1", doc_type=DocType.file, file_type=FileType.image,
                    path="/path/book-p1.jpg", status=Status.completed,
                    parent_id=parent.id, sequence=1)
    lines = LINES[:count]
    page.page_content = "\n".join(lines) + "\n"  # what the first transcription promoted
    db.save(page)
    content, boxes, pos = "", [], 0
    for i, text in enumerate(lines):
        boxes.append(line_box(i, pos, text))
        content += text + "\n"
        pos += len(text) + 1
    artifact = Artifact(
        document_id=page.id, artifact_type="transcription", provider="openai", model="gpt-4o",
        content=content,
        ocr_geometry=OCRGeometryResult(provider="openai", text=content, boxes=boxes),
    )
    db.save(artifact)
    return parent, page, artifact
