"""The Reader draws scripts macOS has no font for, from fonts the engine bundles (#5210, #5206).

On 2026-09-28 the maintainer saw MUFI private-use letters (e.g. U+F1AC on clm 13027 f.38r)
drawn as ▦ in the Reader and ⍰ in the Inspector: the system fonts have no glyphs for them.
The engine now bundles SIL-OFL fonts for what macOS lacks and the Reader's page names them as
fallbacks. If a font file, its licence, its route or its @font-face goes missing, the boxes
come back -- these tests say which link broke.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fichero_server.api.routes.system.views import BUNDLED_FONTS

FONTS_DIR = Path(__file__).resolve().parents[3] / "src" / "fichero_server" / "resources" / "fonts"
TEMPLATE = FONTS_DIR.parents[1] / "api" / "templates" / "document_view.html"


@pytest.mark.parametrize("name", sorted(BUNDLED_FONTS))
def test_each_bundled_font_is_on_disk_with_its_licence_and_provenance(name):
    assert (FONTS_DIR / name).is_file(), f"{name} is in the allowlist but not bundled"
    provenance = (FONTS_DIR / "PROVENANCE.md").read_text(encoding="utf-8")
    assert name in provenance, f"{name} has no provenance row (source, sha256)"
    licences = [p.read_text(encoding="utf-8") for p in FONTS_DIR.glob("OFL-*.txt")]
    assert licences and all("SIL OPEN FONT LICENSE Version 1.1" in text for text in licences), (
        "every bundled font must ship its OFL 1.1 licence; an NC or unknown licence may not be vendored"
    )


@pytest.mark.parametrize("name,media_type", sorted(BUNDLED_FONTS.items()))
def test_the_engine_serves_each_bundled_font(client, name, media_type):
    response = client.get(f"/view/fonts/{name}")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == media_type
    assert response.content == (FONTS_DIR / name).read_bytes()


@pytest.mark.parametrize("name", ["views.py", "../routes/system/views.py", "..%2F..%2Fmain.py", "OFL-Junicode.txt"])
def test_the_font_route_serves_nothing_but_the_allowlist(client, name):
    """Only the named fonts: never another file of the engine, a licence, or a traversal."""
    assert client.get(f"/view/fonts/{name}").status_code == 404


def test_the_readers_page_names_every_bundled_font_as_a_fallback():
    html = TEMPLATE.read_text(encoding="utf-8")
    faces = re.findall(r'url\("/view/fonts/([^"]+)"\)', html)
    assert sorted(faces) == sorted(BUNDLED_FONTS), "every bundled font needs its @font-face, and no face may name a missing one"
    system = re.search(r"--font-system:([^;]+);", html).group(1)
    assert "var(--font-fallbacks)" in system, "the fallbacks must be in the Reader's own font stack"
    assert system.index("system-ui") < system.index("var(--font-fallbacks)"), (
        "the system font draws first; the bundled fonts fill only what it lacks"
    )
