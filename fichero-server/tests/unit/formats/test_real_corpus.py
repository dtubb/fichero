"""Every file in `fixtures/corpus/` through OUR export (#5130, #4944).

**Every format defect found so far came from somebody else's file**, and none from a
round trip through our own writer — a round trip only proves we can read what we
wrote. So this module takes a corpus of pages written by OTHER people's software, in
many scripts and directions and in whatever version of the format they arrived in, and
runs each one through exactly the entry points the importer and exporter use
(`format_for`, `read_page`, `write_page`, `validate`). No second path.

**What is under test is OUR export.** Every real file, whatever version it arrives
in, must import, go out through our writer, and come out valid against the schema we
export (the latest we vendor) — with nothing lost that the loss report does not name.
An old-version file is MORE valuable here, not less: a PAGE 2013 Transkribus page going
out as valid PAGE 2019 is exactly the path a real user walks.

A third-party file that is invalid by its OWN schema, or in an old version, is
information about that file. It is recorded in `fixtures/corpus/CORPUS.md` and is never
a failing test here. Only three outcomes fail:

1. an import that raises (or reads nothing);
2. an export of ours that does not validate (`write_page` refuses to write it);
3. a loss the report does not name — every segment kind, language, direction, script
   and reading text that went in either comes back out or is NAMED.

The corpus directory is GLOBBED, so a file dropped into it is covered with no edit to
this module. **Never edit a corpus file**: a file we edited to make it pass tests our
idea of the file, and our idea is the thing under test.

A real file we cannot handle is listed in `tests/known_specification_failures.txt`
under #5130 (strict xfail), with a line saying what the file does that we do not — so a
fix fails the test and says "delete this line". Do NOT fix a reader from this module.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from fichero_server.formats import (
    SourcePage,
    format_for,
    format_named,
    read_page,
    validate,
    write_page,
)

pytestmark = pytest.mark.source_model

CORPUS = Path(__file__).parent / "fixtures" / "corpus"

#: The scan floor. **A parametrised test over an empty directory passes by testing
#: nothing** — a test elsewhere did exactly that the day this was written, because its
#: directory did not exist. Raise this when files are added; never lower it to make a
#: removal pass.
MIN_FILES = 17

#: Which format a file claims to be, from the `<producer>_<script>_<id>.<fmt>.xml`
#: naming rule in CORPUS.md. The BYTES must agree (`format_for` sniffs), and the first
#: test below asserts they do — a name that lied would test the wrong reader.
SUFFIX_FORMAT = {
    ".page.xml": "pagexml",
    ".alto.xml": "alto",
    ".tei.xml": "tei",
    ".hocr.xml": "hocr",
    ".hocr": "hocr",
}


def _corpus_files() -> list[Path]:
    if not CORPUS.is_dir():
        return []
    return sorted(
        path
        for path in CORPUS.iterdir()
        if path.is_file() and any(path.name.endswith(suffix) for suffix in SUFFIX_FORMAT)
    )


FILES = _corpus_files()


def _claimed_format(path: Path) -> str:
    for suffix, name in SUFFIX_FORMAT.items():
        if path.name.endswith(suffix):
            return name
    raise AssertionError(f"{path.name} does not follow the corpus naming rule")


@pytest.fixture(params=FILES, ids=[path.name for path in FILES])
def corpus_file(request) -> tuple[Path, str, bytes]:
    path: Path = request.param
    return path, _claimed_format(path), path.read_bytes()


class TestTheCorpusIsThere:
    def test_the_directory_exists_and_holds_the_floor(self):
        """The guard against passing vacuously: no directory, or a nearly empty one,
        is a FAILURE here rather than zero parametrised tests nobody notices."""
        assert CORPUS.is_dir(), f"{CORPUS} does not exist -- the corpus tests below ran over nothing"
        assert len(FILES) >= MIN_FILES, (
            f"{len(FILES)} corpus files, floor is {MIN_FILES}: files were removed "
            "or renamed out of the naming rule"
        )

    def test_every_file_has_a_provenance_row(self):
        """A vendored file with no recorded source and licence is a licence question
        nobody can answer later -- and git history is permanent."""
        provenance = (CORPUS / "CORPUS.md").read_text(encoding="utf-8")
        missing = [path.name for path in FILES if f"`{path.name}`" not in provenance]
        assert missing == [], f"no CORPUS.md row for: {missing}"

    def test_nothing_else_is_in_the_directory(self):
        """A file that misses the naming rule would be silently skipped by the glob."""
        stray = [
            path.name
            for path in CORPUS.iterdir()
            if path.is_file() and path.name != "CORPUS.md" and path not in FILES
        ]
        assert stray == [], f"not covered by the corpus glob (naming rule): {stray}"


class TestEachRealFile:
    def test_the_bytes_say_the_format_the_name_says(self, corpus_file):
        path, claimed, data = corpus_file
        spec = format_for(path.name, data)

        assert spec is not None, f"{path.name}: no format recognised these bytes"
        assert spec.name == claimed

    def test_it_imports(self, corpus_file):
        path, claimed, data = corpus_file
        page = read_page(claimed, data)

        assert isinstance(page, SourcePage)
        assert page.segments, f"{path.name}: read without error and produced NOTHING"

    def test_our_export_validates_against_the_schema_we_export(self, corpus_file):
        """Whatever version the file arrived in. `write_page` raises `InvalidExport`
        rather than return an invalid file; the explicit `validate` states the claim
        where it can be read."""
        path, claimed, data = corpus_file
        page = read_page(claimed, data)

        written, _report = write_page(claimed, page)

        assert validate(format_named(claimed), written) == []

    def test_the_loss_report_accounts_for_everything_that_did_not_come_back(self, corpus_file):
        path, claimed, data = corpus_file
        page = read_page(claimed, data)

        written, report = write_page(claimed, page)
        back = read_page(claimed, written)
        lost = " | ".join(sorted(report.lost))

        silent: list[str] = []

        kinds_in = Counter(segment.kind for segment in page.segments)
        kinds_out = Counter(segment.kind for segment in back.segments)
        for kind, count in kinds_in.items():
            if kinds_out[kind] < count and f"{kind} segments" not in report.lost:
                silent.append(f"{count - kinds_out[kind]} of {count} {kind} segments")

        for fact in ("language", "direction", "script"):
            before = _stated(page, fact)
            after = _stated(back, fact)
            if before - after and fact not in lost:
                silent.append(f"{fact} {sorted(before - after)}")

        texts_in = _texts(page)
        texts_out = _texts(back)
        missing = texts_in - texts_out
        if missing and not any(word in lost for word in ("reading", "text", "segments", "markup", "words")):
            silent.append(f"{len(missing)} of {len(texts_in)} reading texts, e.g. {sorted(missing)[:2]}")

        assert silent == [], (
            f"{path.name}: lost without the loss report naming it: {silent}; "
            f"report named: {sorted(report.lost)}"
        )


def _stated(page: SourcePage, fact: str) -> set[str]:
    """Every value of `language` / `direction` / `script` the page states, page-level
    and per segment. A `readingDirection` the model has no value for rides in
    `foreign`, and is counted: it is still a fact the file stated."""
    values = {getattr(page, fact)} | {getattr(segment, fact) for segment in page.segments}
    if fact == "direction":
        values |= {segment.foreign.get("readingDirection") for segment in page.segments}
    return {value for value in values if value}


def _texts(page: SourcePage) -> set[str]:
    return {text for segment in page.segments for _kind, text in segment.readings if text and text.strip()}
