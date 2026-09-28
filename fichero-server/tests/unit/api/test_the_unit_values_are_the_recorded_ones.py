"""Every unit conversion that says it is verified equals the value in a recorded copy of its
public-domain source; every one that is not says so in the answer (maps D10 follow-up, ruled
2026-09-28; `source.geo.historical-units`).

WHY: a number cited "from knowledge" is the numbers-in-comments trap -- it propagates, and nobody can
check it. The relative-place areas are only as good as these lengths: a verst 20 cm off per unit is
two kilometres over a hundred versts. So each value is read back from the source's own words
(NIST Handbook 44's tables; Brockhaus-Efron's «Верста»), and a value with no recorded source is
labelled "cited, not verified" wherever it is used. If this regresses, a length drifts from its
source unseen, or an unchecked one is presented as checked.

The recorded texts are in `fixtures/units/` (PROVENANCE.md), read here with plain json and re.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fichero_server.knowledge.units import UNITS, resolve_distance

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "units"
NIST = json.loads((FIXTURES / "nist_hb44_2024_appendix_c.json").read_text())["lines"]
ESBE = json.loads((FIXTURES / "esbe_versta.json").read_text())["verst"]


def _number(text: str) -> float:
    """A number as the source prints it: thin spaces between digit groups, a decimal comma."""
    return float(text.replace(" ", "").replace(",", "."))


def test_the_mile_and_the_league_are_nist_s():
    [mile_row] = [line for line in NIST["C-10"] if line.startswith("1 mile")]
    assert UNITS["mile"].conversion("statute").metres == _number(mile_row.rsplit(" ", 1)[1]) == 1609.344
    foot = re.search(r"= (0\.304 8) \(exactly\)", NIST["C-10"][1]).group(1)
    assert "= 5280 feet" in NIST["C-5"][0] and 5280 * _number(foot) == 1609.344            # the mile, from the foot
    [league_row] = NIST["C-11"]
    league_m = _number(re.search(r"= (\d[\d ]*\.\d+)", league_row).group(1).strip())
    assert UNITS["league"].conversion("land").metres == league_m == 4828.032
    assert "= 3 miles" in NIST["C-5"][1]
    assert UNITS["mile"].conversion().verified and UNITS["league"].conversion().verified


def test_the_verst_is_brockhaus_efron_s():
    recorded = _number(re.search(r"равна ([\d,]+) метр", ESBE).group(1))
    assert "500 саженей" in ESBE
    assert UNITS["verst"].conversion("1835").metres == recorded == 1066.781
    assert UNITS["verst"].conversion().verified


def test_a_value_with_no_recorded_source_says_so_in_the_answer():
    for key in ("legua", "vara"):
        for conversion in UNITS[key].conversions:
            assert conversion.verified is False, (key, conversion.key)
    answer = resolve_distance(21, "legua")
    assert answer["verified"] is False and "cited, not verified" in answer["source"]
    assert resolve_distance(3, "league")["verified"] is True
