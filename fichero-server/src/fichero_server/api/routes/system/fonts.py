"""The fonts the engine ships, for scripts the system fonts leave as ⍰ or ▦ (#5210, #5206).

A MUFI line of Clm 13027 (U+F1AC, a Private Use abbreviation) drew as a box in the Reader: no
system font has MUFI's letters, and Syriac, Mongolian, Coptic and Cherokee are patchy. These are
FALLBACKS -- `document_view.html` names them after the system stack, so a glyph the system font
has is drawn by it and only a missing one reaches this set.

Served by the engine rather than read from a path because the engine may be remote (the app's
web view fetches `/api/fonts/<file>` through its authenticated scheme handler, as it fetches
thumbnails). The app registers the SAME files for the Inspector and labels, from `GET /api/fonts`.

Every file is the upstream release, unmodified, under the SIL Open Font License 1.1, with its
own OFL text beside it; source, version and sha256 are in `resources/fonts/PROVENANCE.md`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/fonts", tags=["fonts"])

FONT_DIR = Path(__file__).resolve().parents[3] / "resources" / "fonts"

#: family, file, what it is for, its licence file. The ORDER is the fallback order.
FONTS: tuple[tuple[str, str, str, str], ...] = (
    ("Junicode", "Junicode-Regular.otf", "Medieval Latin: MUFI characters and abbreviations", "OFL-Junicode.txt"),
    ("Noto Sans Syriac", "NotoSansSyriac-Regular.otf", "Syriac, Estrangela", "OFL-NotoSansSyriac.txt"),
    ("Noto Sans Syriac Western", "NotoSansSyriacWestern-Regular.otf", "Syriac, Serto", "OFL-NotoSansSyriacWestern.txt"),
    ("Noto Sans Syriac Eastern", "NotoSansSyriacEastern-Regular.otf", "Syriac, Eastern", "OFL-NotoSansSyriacEastern.txt"),
    ("Noto Sans Mongolian", "NotoSansMongolian-Regular.otf", "Mongolian", "OFL-NotoSansMongolian.txt"),
    ("Noto Sans Coptic", "NotoSansCoptic-Regular.otf", "Coptic", "OFL-NotoSansCoptic.txt"),
    ("Noto Sans Cherokee", "NotoSansCherokee-Regular.otf", "Cherokee", "OFL-NotoSansCherokee.txt"),
)

#: Only these names are served: a request names a file from this list or gets a 404, so no
#: path a client sends ever reaches the disk.
_SERVED = {file: "font/otf" for _f, file, _p, _l in FONTS} | {
    licence: "text/plain; charset=utf-8" for _f, _file, _p, licence in FONTS
}


class BundledFont(BaseModel):
    family: str
    #: The engine path to fetch it from, relative to the engine's origin.
    url: str
    format: str = "opentype"
    covers: str
    licence_url: str


@router.get("", response_model=list[BundledFont])
async def list_fonts() -> list[BundledFont]:
    """The bundled fallback fonts, in fallback order."""
    return [
        BundledFont(family=family, url=f"/api/fonts/{file}", covers=covers, licence_url=f"/api/fonts/{licence}")
        for family, file, covers, licence in FONTS
    ]


@router.get("/{name}")
async def font_file(name: str) -> FileResponse:
    """One bundled font file, or its licence."""
    media_type = _SERVED.get(name)
    if media_type is None:
        raise HTTPException(status_code=404, detail=f"No bundled font named {name!r}")
    # Immutable: a changed font ships under a new file name, never the same one.
    return FileResponse(
        FONT_DIR / name, media_type=media_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


def font_face_css() -> str:
    """`@font-face` rules for every bundled font, for a page the engine serves."""
    return "\n".join(
        f'@font-face {{ font-family: "{family}"; src: url("/api/fonts/{file}") format("opentype"); '
        "font-display: swap; }"
        for family, file, _covers, _licence in FONTS
    )


#: The families as a CSS font-family tail, in fallback order.
FALLBACK_FAMILIES = ", ".join(f'"{family}"' for family, *_rest in FONTS)
