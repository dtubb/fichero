"""The engine's bundled fallback fonts reach the Reader (#5210, #5206).

WHY: the MUFI abbreviation U+F1AC on Clm 13027 f. 38r drew as ▦ in the Reader -- no system font
has MUFI's Private Use letters -- and Syriac, Mongolian, Coptic and Cherokee are patchy. The
engine now ships OFL fonts that cover them and names them in the Reader's font stack after the
system fonts. If this regresses, those letters are boxes again; if the files drift from their
recorded upstream hashes, the licence and provenance note no longer describe what ships.

Coverage is read from each font's own `cmap` with a small reader here (fontTools is not in the
gate's venv), so "Junicode covers U+F1AC" is a fact about the file, not a belief.
"""

from __future__ import annotations

import hashlib
import re
import struct
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import fichero_server.api.main  # noqa: F401  (registers every route)
from fichero_server.api.auth import attach_auth_middleware
from fichero_server.api.routes.system import fonts
from fichero_server.api.routes.system.fonts import FONT_DIR, FONTS
from tests.unit.api.test_page_text_follows_the_file import _import

MUFI_PAGE = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus" / "escriptorium_latin-mufi_clm13027-38r.alto.xml"
#: A letter of each script, and the family that must draw it.
SAMPLES = {
    "Junicode": "",                    # MUFI, the letter that drew as a box
    "Noto Sans Syriac": "ܐ",            # ܐ
    "Noto Sans Syriac Western": "ܐ",
    "Noto Sans Syriac Eastern": "ܐ",
    "Noto Sans Mongolian": "ᠠ",         # ᠠ
    "Noto Sans Coptic": "ⲁ",            # ⲁ
    "Noto Sans Cherokee": "Ꭰ",          # Ꭰ
}


def covered(font: bytes) -> set[int]:
    """Every code point an sfnt's Unicode cmap maps to a real glyph (formats 4 and 12)."""
    num_tables = struct.unpack_from(">H", font, 4)[0]
    tables = {font[12 + 16 * i:16 + 16 * i]: struct.unpack_from(">II", font, 20 + 16 * i) for i in range(num_tables)}
    base = tables[b"cmap"][0]
    subtables = {}
    for i in range(struct.unpack_from(">H", font, base + 2)[0]):
        platform, encoding, offset = struct.unpack_from(">HHI", font, base + 4 + 8 * i)
        subtables[(platform, encoding)] = base + offset
    points: set[int] = set()
    for at in subtables.values():
        kind = struct.unpack_from(">H", font, at)[0]
        if kind == 12:
            for g in range(struct.unpack_from(">I", font, at + 12)[0]):
                start, end, glyph = struct.unpack_from(">III", font, at + 16 + 12 * g)
                points.update(c for c in range(start, end + 1) if glyph + c - start)
        elif kind == 4:
            segs = struct.unpack_from(">H", font, at + 6)[0] // 2
            ends = struct.unpack_from(f">{segs}H", font, at + 14)
            starts = struct.unpack_from(f">{segs}H", font, at + 16 + 2 * segs)
            deltas = struct.unpack_from(f">{segs}h", font, at + 16 + 4 * segs)
            ranges_at = at + 16 + 6 * segs
            ranges = struct.unpack_from(f">{segs}H", font, ranges_at)
            for s, (start, end, delta, rng) in enumerate(zip(starts, ends, deltas, ranges)):
                for c in range(start, end + 1):
                    if rng == 0:
                        glyph = (c + delta) & 0xFFFF
                    else:
                        glyph = struct.unpack_from(">H", font, ranges_at + 2 * s + rng + 2 * (c - start))[0]
                        glyph = (glyph + delta) & 0xFFFF if glyph else 0
                    if glyph and c != 0xFFFF:
                        points.add(c)
    return points


def _file(family: str) -> bytes:
    return (FONT_DIR / next(f for fam, f, *_ in FONTS if fam == family)).read_bytes()


def test_each_file_is_the_recorded_upstream_release_with_its_ofl_beside_it():
    provenance = (FONT_DIR / "PROVENANCE.md").read_text(encoding="utf-8")
    for family, file, _covers, licence in FONTS:
        digest = hashlib.sha256((FONT_DIR / file).read_bytes()).hexdigest()
        row = next(line for line in provenance.splitlines() if line.startswith(f"| `{file}`"))
        assert digest in row, (file, digest)
        assert "SIL OPEN FONT LICENSE Version 1.1" in (FONT_DIR / licence).read_text(encoding="utf-8")


def test_each_font_draws_its_script():
    for family, letter in SAMPLES.items():
        assert ord(letter) in covered(_file(family)), (family, hex(ord(letter)))
    # The reader can say NO: a Coptic font has no MUFI and Junicode no Mongolian.
    assert 0xF1AC not in covered(_file("Noto Sans Coptic"))
    assert 0x1820 not in covered(_file("Junicode"))


def test_every_mufi_letter_on_clm_13027_38r_has_a_bundled_font():
    text = MUFI_PAGE.read_text(encoding="utf-8")
    private = {ord(c) for c in text if 0xE000 <= ord(c) <= 0xF8FF}
    assert 0xF1AC in private                                  # the premise, from the file
    assert private <= covered(_file("Junicode")), sorted(hex(c) for c in private - covered(_file("Junicode")))


def test_the_routes_serve_the_files_and_nothing_else(client):
    listed = client.get("/api/fonts").json()
    assert [f["family"] for f in listed] == [family for family, *_ in FONTS]
    for entry in listed:
        response = client.get(entry["url"])
        assert response.status_code == 200 and response.headers["content-type"] == "font/otf"
        assert response.content == (FONT_DIR / entry["url"].rsplit("/", 1)[1]).read_bytes()
        assert "immutable" in response.headers["cache-control"]
        licence = client.get(entry["licence_url"])
        assert licence.status_code == 200 and licence.headers["content-type"].startswith("text/plain")
    for name in ("PROVENANCE.md", "..%2F..%2Fapi%2Fmain.py", "missing.otf"):
        assert client.get(f"/api/fonts/{name}").status_code == 404, name


def test_the_font_routes_are_behind_the_engines_auth():
    """Fonts hold no library data, but they are not on the unauthenticated list either: the app's
    web view fetches them through its authenticated scheme handler, like thumbnails."""
    app = FastAPI()
    app.include_router(fonts.router)
    attach_auth_middleware(app, token="secret")
    anonymous = TestClient(app)
    assert anonymous.get("/api/fonts").status_code == 401
    assert anonymous.get("/api/fonts/Junicode-Regular.otf").status_code == 401
    ok = anonymous.get("/api/fonts/Junicode-Regular.otf", headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200


def test_the_reader_page_declares_every_face_and_names_them_after_the_system_fonts(db, client):
    doc_id = _import(db, MUFI_PAGE)
    page = client.get(f"/view/document/{doc_id}").text
    for family, file, *_ in FONTS:
        assert f'font-family: "{family}"; src: url("/api/fonts/{file}")' in page, family
    stack = re.search(r"--font-system:([^;]+);", page).group(1)
    assert stack.index("system-ui") < stack.index('"Junicode"') < stack.index("sans-serif"), stack
