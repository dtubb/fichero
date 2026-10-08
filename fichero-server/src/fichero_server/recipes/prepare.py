"""Image preparation as a recipe step (`source.onboard.auto.prepare-damaged-images`, #5580).

Where the project's sample shows faded pages, setup proposes `prepare-the-image` as a step; Start runs it as its own
card (`prepare`) after any split and before lines. Each faded page gets a NEW rendition (role `prepared`, the page's
own frame: `transform` None, never primary) with its contrast raised; the original file is never written to. The
steps after it, lines and reading, read that rendition in place of the original (`vision_base.frame_true_rendition_path`),
and a page already prepared is not prepared again.

ponytail: "faded" is one measured number, the spread between the page's darkest and lightest 1% of grey
(`contrast_spread`), below `FADED_BELOW`. It sees faded ink and a washed-out scan; it does not see stains, holes,
uneven light or a tilt, and a near-blank page with only a few faint marks reads as faded. Deskew is not done: a
straightened picture is not the page's frame, so lines found on it would not map back to the original until the
frame-identity work lets a rendition carry its transform to the lines. Upgrade path: the bake-off measuring each
operation's effect on reading (`prep.judged-by-reading`), and the image-preparation spec's operations as cards.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

#: The rendition role the step writes, and the steps after it read.
ROLE = "prepared"
#: A page whose grey spread (darkest 1% to lightest 1%, of 255) is below this is faded. A clean scan or photograph
#: of ink on paper spreads well over 150; faded ink on yellowed paper, under 100.
FADED_BELOW = 100
#: Below this spread there is nothing on the page to raise: a blank page is not faded.
BLANK_BELOW = 16
#: How many pages setup looks at: up to ten, spread across the material (`source.onboard.samples-first`).
SAMPLE_PAGES = 10
_WIDTH = 400


def _grey(path: str | None) -> Any | None:
    """The page as a small grey picture, or None when there is no image to look at."""
    if not path or not Path(path).is_file():
        return None
    from PIL import Image, ImageOps

    try:
        with Image.open(path) as image:
            image.draft("L", (_WIDTH * 2, _WIDTH * 2))
            grey = ImageOps.grayscale(image)
            grey.thumbnail((_WIDTH, _WIDTH * 2))
            return grey
    except OSError:
        return None


def contrast_spread(path: str | None) -> int | None:
    """The spread between the page's darkest and lightest 1% of grey (0-255), or None with no image to look at."""
    grey = _grey(path)
    if grey is None:
        return None
    histogram, total = grey.histogram(), grey.width * grey.height
    cut = max(1, total // 100)

    def level(levels) -> int:
        seen = 0
        for value in levels:
            seen += histogram[value]
            if seen >= cut:
                return value
        return 0

    return level(range(255, -1, -1)) - level(range(256))


def is_faded(path: str | None) -> bool:
    spread = contrast_spread(path)
    return spread is not None and BLANK_BELOW <= spread < FADED_BELOW


def sample(db: Any) -> list[Any]:
    """Up to `SAMPLE_PAGES` of the project's pages, spread evenly from the first to the last."""
    from fichero_server.models import Document

    ids = db.unit_of_work_ids()
    if len(ids) > SAMPLE_PAGES:
        step = (len(ids) - 1) / (SAMPLE_PAGES - 1)
        ids = [ids[round(i * step)] for i in range(SAMPLE_PAGES)]
    return [doc for doc in (db.get(Document, i) for i in ids) if doc is not None]


def sample_shows_faded(db: Any) -> bool:
    """Whether any page of the project's sample is faded: setup then proposes preparing the images."""
    return any(is_faded(doc.path) for doc in sample(db))


#: Files that are text already: nothing reads them (`source.recipe.text-material-is-not-read`, #5553).
TEXT_FILE_TYPES = frozenset({"text", "word", "docx", "epub"})


def is_text(db: Any, doc: Any) -> bool:
    """Whether this page or file is already text: a text file (Markdown, plain text, Word, an e-book), or a PDF's page
    whose text layer the import kept (its `text_geometry` artifact has boxes). A scanned PDF page has none."""
    from fichero_server.importers.ingest import PDF_TEXT_GEOMETRY_ARTIFACT
    from fichero_server.models import Artifact

    if str(getattr(doc.file_type, "value", doc.file_type) or "") in TEXT_FILE_TYPES:
        return True
    return any((a.data or {}).get("box_count") for a in
               db.query(Artifact, document_id=doc.id, artifact_type=PDF_TEXT_GEOMETRY_ARTIFACT))


def sample_is_text(db: Any) -> bool:
    """Whether every page of the project's sample is already text: setup then reads none of it (#5553)."""
    docs = sample(db)
    return bool(docs) and all(is_text(db, doc) for doc in docs)


def prepared(db: Any, doc_id: str) -> Any | None:
    """The page's prepared rendition, if it has one."""
    from fichero_server.models import Rendition

    return next((r for r in db.query(Rendition, document_id=doc_id) if r.role == ROLE), None)


def prepare_pages(db: Any, documents: list[str], run_id: str) -> dict[str, int]:
    """Prepare each faded page of `documents` as a new rendition; the account of what it did: `prepared`, `clear`
    (not faded, left alone), `no_image` (nothing to look at: a PDF's page, a text file)."""
    from PIL import Image, ImageOps

    from fichero_server.models import Document, Rendition

    library = Path(db.path).parent
    account = {"prepared": 0, "clear": 0, "no_image": 0}
    for doc_id in documents:
        doc = db.get(Document, doc_id)
        spread = contrast_spread(doc.path if doc is not None else None)
        if spread is None:
            account["no_image"] += 1
            continue
        if not BLANK_BELOW <= spread < FADED_BELOW:
            account["clear"] += 1  # clear enough, or blank: nothing to raise
            continue
        relative = Path("files") / ROLE / f"{doc.id}.png"
        with Image.open(doc.path) as image:
            # The original's own pixels and orientation tag: the same frame, so the lines found on it are the page's.
            exif = image.getexif()
            base = image if image.mode in ("RGB", "L") else image.convert("RGB")
            # The faded ink raised: the darkest 1% to black, the lightest 1% to white (the measure's own cut).
            out = ImageOps.autocontrast(base, cutoff=1)
        (library / relative).parent.mkdir(parents=True, exist_ok=True)
        out.save(library / relative, format="PNG", exif=exif)
        db.save(Rendition(document_id=doc.id, role=ROLE, path=str(relative), is_primary=False,
                          pixel_width=out.width, pixel_height=out.height, producer_run_id=run_id,
                          producer_tool="prepare-the-image",
                          note=f"faded (grey spread {spread}/255): contrast raised"))
        account["prepared"] += 1
    return account
