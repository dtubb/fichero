"""`source.onboard.direction-chosen` (#5479) and `source.recipe.nothing-assumes-spaces-direction-or-an-alphabet`
(#5728): Find Lines reads the direction the project chose. Kraken's segmenter is told it (`text_direction`), so a
right-to-left page's lines are ordered from the right and a page in columns is found in columns.

WHY: Kraken was always told `horizontal-lr`, whatever setup said: a vertical page's columns were looked for as
rows and a Hebrew page's lines ordered from the left.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.llm import kraken_runtime
from fichero_server.models import DocType, Document
from fichero_server.workflows.tools.vision_base import page_direction


@pytest.mark.parametrize("direction, said", [
    ("rtl", {"text_direction": "horizontal-rl"}), ("ttb", {"text_direction": "vertical-rl"}),
    ("ttb-lr", {"text_direction": "vertical-lr"}), ("ltr", {}), (None, {}), ("alternating", {}),
])
def test_each_direction_is_said_in_kraken_words(direction, said):
    assert kraken_runtime.text_direction(direction) == said


def test_the_page_direction_reaches_the_segmenter_and_none_leaves_it_alone(monkeypatch):
    seen = []
    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda image_path, **kw: seen.append(kw) or
                        {"width": 10, "height": 10, "lines": [], "regions": []})
    kraken_runtime.segment_to_geometry("/p.png", direction="rtl")
    kraken_runtime.segment_to_geometry("/p.png")
    assert seen == [{"direction": "rtl"}, {}]


@pytest.mark.parametrize("scripts, languages, directions, said", [
    (["Hebr"], ["he"], None, {"direction": "rtl"}),
    (["Hebr"], ["he"], {"Hebr": "ltr"}, {}),  # changed in setup: the person's answer, not the script's
    (["Hant"], ["zh"], None, {"direction": "ttb"}),
    (["Latn"], ["es"], None, {}),
])
def test_a_page_takes_the_direction_setup_holds_for_the_projects_script(client, db, scripts, languages, directions,
                                                                         said):
    page = Document(name="p1.png", doc_type=DocType.file)
    db.save(page)
    answers = {"purpose": "transcribe", "languages": languages, "scripts": scripts, "material": "handwriting",
               **({"directions": directions} if directions else {})}
    r = client.put("/api/recipes/project", json={"answers": answers, "recipe": None})
    assert r.status_code == 200, r.text
    assert page_direction(str(Path(db.path).parent), page.id) == said


def test_no_page_has_no_direction(db):
    assert page_direction(str(Path(db.path).parent), "no-such-page") == {} and page_direction(None, "x") == {}
