"""Every format that writes is validated against somebody else's file, and the
directory check says what it did NOT check.

Two things live here because they fail together. `scripts/validate_exports.py` is
the one command for "will this export open elsewhere", and the guard below is what
stops a sixth format shipping with no validation behind it: it is parametrised over
`known_formats()`, so registering a format ADDS a case, and the case fails until
the format has a real third-party fixture or a stated reason it has no schema.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from fichero_server.formats import format_for, known_formats, read_page, write_page

_FIXTURES = Path(__file__).parent / "fixtures"
_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "validate_exports.py"
_SPEC = importlib.util.spec_from_file_location("validate_exports", _SCRIPT)
assert _SPEC and _SPEC.loader
script = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = script
_SPEC.loader.exec_module(script)

#: Formats with no schema BY NATURE, and why. A format lands here by a reviewed edit
#: with a reason, never by leaving `schema=None` -- that is the vacuous pass.
SCHEMALESS = {
    "hocr": "a microformat over HTML; there is no XSD. Real engine output is on the "
    "'Still wanted' list in fixtures/PROVENANCE.md (licences refused so far).",
    "yolo": "lines of numbers; nothing to validate but the arithmetic, which "
    "test_hocr_and_yolo.py pins.",
}

#: Real files by format, identified by their BYTES, not their names.
_REAL = {}
for _path in sorted(_FIXTURES.glob("*.xml")):
    _spec = format_for(_path.name, _path.read_bytes())
    if _spec is not None:
        _REAL.setdefault(_spec.name, []).append(_path)


@pytest.mark.parametrize("spec", [s for s in known_formats() if s.writes], ids=lambda s: s.name)
def test_a_format_that_writes_has_a_schema_or_says_why_not(spec):
    """A new format registered with `schema=None` and no entry here fails: it would
    otherwise export forever with nothing checking a single byte."""
    if spec.schema is None:
        assert spec.name in SCHEMALESS, (
            f"{spec.name} writes files and has no schema. Vendor one "
            "(schemas/PROVENANCE.md) or add it to SCHEMALESS with the reason."
        )
    else:
        assert spec.name not in SCHEMALESS, f"{spec.name} has a schema now; drop it from SCHEMALESS"


@pytest.mark.parametrize(
    "spec", [s for s in known_formats() if s.writes and s.schema], ids=lambda s: s.name
)
def test_a_format_with_a_schema_validates_a_file_somebody_else_wrote(spec):
    """At least one third-party file validates as-is. Without one, a schema that
    rejects everything real -- or a reader that never meets real input -- ships
    unnoticed: our own writer and our own reader agree with each other perfectly."""
    outcomes = [script.check(path)[0] for path in _REAL.get(spec.name, [])]
    assert "valid" in outcomes, (
        f"no third-party {spec.name} file in fixtures/ validates against "
        f"{spec.schema} (outcomes: {outcomes or 'no files'}). Vendor one, licence first."
    )


@pytest.mark.parametrize("path", [p for ps in _REAL.values() for p in ps], ids=lambda p: p.name)
def test_every_real_file_re_exports_valid(path):
    """Read somebody else's file, write it in the same format: the export passes our
    own schema check. `write_page` raises InvalidExport otherwise. This is what
    found the TableCell defect -- a real table page, exported invalid."""
    name = format_for(path.name, path.read_bytes()).name
    data, _ = write_page(name, read_page(name, path.read_bytes()))
    assert script.check_bytes(path.name, data)[0] == "valid"


class TestTheScriptSaysWhatItDidNotCheck:
    def test_an_older_version_is_neither_valid_nor_invalid(self):
        """PAGE 2013 against the 2019 schema fails every element; that is a fact
        about the schemas we ship, and calling it INVALID would blame the file."""
        outcome, name, problems = script.check(_FIXTURES / "tarima_arabic_0498.page.xml")
        assert (outcome, name) == ("other version", "pagexml")
        assert "2013-07-15" in problems[0]

    def test_alto_4_3_is_told_from_4_2_by_the_file_it_declares(self):
        """ALTO keeps one namespace for all of 4.x; only the declared schema file
        says which. Kraken writes 4.3 (ReadingOrder), which 4.2 rejects."""
        outcome, _, problems = script.check(_FIXTURES / "kraken_alto_multilingual_bsb00084914.alto.xml")
        assert outcome == "other version"
        assert "alto-4-3.xsd" in problems[0]

    def test_a_broken_export_is_invalid_with_the_schemas_own_words(self, tmp_path):
        data = (_FIXTURES / "ocrd_gt_aepinus_0020.page.xml").read_text(encoding="utf-8")
        broken = data.replace("<Page ", "<Page bogusAttribute=\"1\" ", 1)
        (tmp_path / "bad.page.xml").write_text(broken, encoding="utf-8")
        outcome, _, problems = script.check(tmp_path / "bad.page.xml")
        assert outcome == "INVALID"
        assert any("bogusAttribute" in p for p in problems)
        assert script.main([str(tmp_path)]) == 1

    def test_a_directory_where_nothing_was_validated_is_not_a_pass(self, tmp_path):
        """Empty, or only files nothing could check: exit 1. Absence of errors
        because nothing was examined is the failure this script exists to prevent."""
        assert script.main([str(tmp_path)]) == 1
        (tmp_path / "notes.txt").write_text("not an export\n", encoding="utf-8")
        assert script.main([str(tmp_path)]) == 1

    def test_the_real_fixtures_pass_as_a_directory(self, capsys):
        assert script.main([str(_FIXTURES)]) == 0
        assert "0 INVALID" in capsys.readouterr().out
