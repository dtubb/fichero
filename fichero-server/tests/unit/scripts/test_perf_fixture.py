"""The speed trial's page is GENERATED, and says what is real (`source.perf.declared-fixture`, #4940).

A generated page described as a real one would be the same lie as a number quoted from a
comment. These make the declaration CHECKABLE: the committed samples are re-measured from
the named real files, and the generated page is held to them.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "perf_fixture.py"
_SPEC = importlib.util.spec_from_file_location("perf_fixture", _SCRIPT)
assert _SPEC and _SPEC.loader
fixture = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = fixture
_SPEC.loader.exec_module(fixture)

COMMITTED = json.loads(fixture.DISTRIBUTION.read_text(encoding="utf-8"))


def test_the_committed_samples_are_what_the_named_real_pages_measure():
    """If a source file or the measuring changes, the fixture's claim about where its numbers
    came from would silently stop being true. It fails here instead."""
    assert fixture.measure() == COMMITTED


def test_the_file_says_it_is_generated_and_names_real_files_that_exist():
    assert COMMITTED["generated"] is True
    assert "GENERATED" in COMMITTED["declaration"] and "Not a real page" in COMMITTED["declaration"]
    for name in COMMITTED["sources"]:
        assert (fixture.FIXTURES / name).is_file(), name


def test_it_reaches_the_ruled_count_with_every_level_of_nesting():
    page = fixture.generate(20000)
    kinds = Counter(s.kind for s in page.segments)
    assert len(page.segments) >= 20000
    assert set(kinds) == {"region", "line", "word", "character"}
    refs = {s.ref for s in page.segments}
    assert all(s.parent_ref in refs for s in page.segments if s.kind != "region")


def test_two_runs_measure_one_page():
    """Deterministic, or a comparison between runs compares two different pages."""
    first = [(s.ref, s.rect) for s in fixture.generate(5000).segments]
    second = [(s.ref, s.rect) for s in fixture.generate(5000).segments]
    assert first == second


def test_relative_sizes_are_the_real_ones():
    """Uniform scaling keeps a word's width over its line's height exactly as sampled."""
    page = fixture.generate(5000)
    by_ref = {s.ref: s for s in page.segments}
    width, height = page.image_size
    sampled = set(COMMITTED["samples"]["word_width_over_line_height"])
    for word in (s for s in page.segments if s.kind == "word"):
        line = by_ref[word.parent_ref]
        ratio = (word.rect[2] * width) / (line.rect[3] * height)
        assert any(abs(ratio - value) < 1e-6 for value in sampled), ratio


def test_the_page_is_on_the_page_and_exports_as_valid_page_xml():
    from fichero_server.formats import write_page

    page = fixture.generate(5000)
    assert all(0 <= r[0] and r[0] + r[2] <= 1.0 + 1e-9 and 0 <= r[1] and r[1] + r[3] <= 1.0 + 1e-9
               for r in (s.rect for s in page.segments))
    data, _ = write_page("pagexml", page)  # validated against PAGE 2019 on the way out
    assert data.count(b"<Glyph") >= 4000


def test_every_shape_has_area_so_the_importer_takes_the_page():
    """A real source page has a zero-width word box; sampled, it made a shape with no area at
    the page's edge and the importer refused the whole fixture. Every generated shape has area."""
    page = fixture.generate(20000)
    assert all(s.rect[2] > 0 and s.rect[3] > 0 for s in page.segments)
