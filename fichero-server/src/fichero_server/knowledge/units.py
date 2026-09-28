"""Historical distance units, each kept with its conversions to metres and where each comes from
(maps D10, #5120; `source.geo.historical-units`).

A distance is stored AS WRITTEN ("tres leguas") with its number and unit; metres are worked out on
read through the conversion the library has chosen, so choosing another conversion re-resolves
every area and rewrites nothing. Sources are public-domain law and government texts only.

The tolerance a resolved area carries is EXPLICIT (ruled 2026-09-28): a unit whose conversions
differ (a legua was not one length) spreads its area by half that spread around the chosen one; a
unit with one conversion carries the stated default below. Either way the answer's `conversion`
says which, so no width is a hidden constant.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Tolerance when a unit has one conversion: a quarter of the stated distance. Historical distances
#: were usually measured along the road, not straight, and rounded ("tres leguas"); a quarter is the
#: stated allowance for both, and says so in every answer that uses it.
DEFAULT_TOLERANCE_FRACTION = 0.25


@dataclass(frozen=True)
class Conversion:
    key: str
    metres: float
    source: str


@dataclass(frozen=True)
class Unit:
    key: str
    label: str
    conversions: tuple[Conversion, ...]
    default: str

    def conversion(self, key: str | None = None) -> Conversion:
        wanted = key or self.default
        for conversion in self.conversions:
            if conversion.key == wanted:
                return conversion
        raise KeyError(f"{self.key} has no conversion {wanted!r}; one of {', '.join(c.key for c in self.conversions)}")


_VARA_CASTELLANA_M = 0.835905     # the vara of Burgos, Spain's legal vara, as fixed when the metric system was adopted
_CASTILE = ("Spain, Ley de 19 de julio de 1849 (the metric system) and its tables of equivalence with the "
            "measures of Castile: vara castellana = 0.835905 m")
_NIST = "NIST Handbook 44, Appendix C (US government, public domain)"

UNITS: dict[str, Unit] = {u.key: u for u in (
    Unit("legua", "legua (Castile)", (
        Conversion("legal", 5000 * _VARA_CASTELLANA_M, f"legua legal of 5000 varas; {_CASTILE}"),
        Conversion("comun", 20000 / 3 * _VARA_CASTELLANA_M, f"legua común of 20000 pies (6666⅔ varas); {_CASTILE}"),
    ), default="legal"),
    Unit("vara", "vara castellana", (Conversion("castellana", _VARA_CASTELLANA_M, _CASTILE),), default="castellana"),
    Unit("mile", "mile (English statute)", (
        Conversion("statute", 1609.344, f"statute mile of 5280 feet, international foot; {_NIST}"),), default="statute"),
    Unit("league", "league (English land)", (
        Conversion("land", 3 * 1609.344, f"league (land) of 3 statute miles; {_NIST}"),), default="land"),
    Unit("verst", "verst (Russia)", (
        Conversion("1835", 500 * 7 * 0.3048,
                   "verst of 500 sazhen, the sazhen fixed at 7 English feet by the Russian weights-and-measures "
                   "law of 1835"),), default="1835"),
    Unit("km", "kilometre", (Conversion("si", 1000.0, "SI"),), default="si"),
    Unit("m", "metre", (Conversion("si", 1.0, "SI"),), default="si"),
)}


class UnknownUnit(ValueError):
    pass


def unit_named(key: str) -> Unit:
    try:
        return UNITS[key]
    except KeyError as exc:
        raise UnknownUnit(f"unknown unit {key!r}; one of {', '.join(sorted(UNITS))}") from exc


def resolve_distance(value: float, unit_key: str, conversion_key: str | None = None) -> dict:
    """The distance in metres through a conversion, with its tolerance and why -- everything the
    answer's `conversion` carries."""
    unit = unit_named(unit_key)
    chosen = unit.conversion(conversion_key)
    metres = value * chosen.metres
    lengths = [c.metres for c in unit.conversions]
    if len(lengths) > 1:
        tolerance = value * (max(lengths) - min(lengths)) / 2
        basis = (f"half the spread of the {unit.label}'s conversions "
                 f"({', '.join(f'{c.key} {c.metres:.1f} m' for c in unit.conversions)})")
    else:
        tolerance = metres * DEFAULT_TOLERANCE_FRACTION
        basis = (f"stated default: ±{DEFAULT_TOLERANCE_FRACTION:.0%} of the distance "
                 "(one conversion; historical distances were measured along roads and rounded)")
    return {"unit": unit.key, "conversion": chosen.key, "metres_per_unit": chosen.metres, "source": chosen.source,
            "distance_m": metres, "tolerance_m": tolerance, "tolerance_basis": basis}
