"""Geocoding: place name → lat/lon (#2266).

Two tiers, cheapest first:

1. A small offline gazetteer covers the places that recur in the archives we
   work with (Spanish-American, Iberian, major world cities) so the common
   case resolves with no network round-trip and tests stay hermetic.
2. Anything the gazetteer misses falls through to Nominatim (OpenStreetMap)
   when ``online=True``. Results are memoised per process.

ponytail: offline gazetteer + opt-in Nominatim. Swap in GeoNames or a paid
geocoder if archive coverage falls short — the public surface
(``geocode`` / ``geocode_places``) stays the same.
"""

from __future__ import annotations

import logging
import unicodedata

from fichero_server.models.knowledge import GeoPoint

logger = logging.getLogger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy requires an identifying User-Agent.
_USER_AGENT = "fichero-server/geocoder (https://github.com/dtubb/fichero)"


def _normalize(name: str) -> str:
    """Casefold + strip accents so 'Popayán' and 'popayan' resolve alike."""
    text = " ".join(str(name or "").split()).strip()
    decomposed = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return folded.casefold()


# Normalized name → (lat, lon). Keep small and archive-relevant; this is a
# convenience cache, not an authority — Nominatim is the fallback.
_GAZETTEER: dict[str, tuple[float, float]] = {
    # Colombia / Spanish America
    "popayan": (2.4448, -76.6147),
    "quito": (-0.1807, -78.4678),
    "bogota": (4.7110, -74.0721),
    "santa fe de bogota": (4.7110, -74.0721),
    "cartagena": (10.3910, -75.4794),
    "cali": (3.4516, -76.5320),
    "medellin": (6.2442, -75.5812),
    "lima": (-12.0464, -77.0428),
    "cusco": (-13.5319, -71.9675),
    "potosi": (-19.5836, -65.7531),
    "mexico city": (19.4326, -99.1332),
    "ciudad de mexico": (19.4326, -99.1332),
    "veracruz": (19.1738, -96.1342),
    "havana": (23.1136, -82.3666),
    "la habana": (23.1136, -82.3666),
    "panama": (8.9824, -79.5199),
    "caracas": (10.4806, -66.9036),
    "buenos aires": (-34.6037, -58.3816),
    "santiago": (-33.4489, -70.6693),
    # Iberia
    "madrid": (40.4168, -3.7038),
    "sevilla": (37.3891, -5.9845),
    "seville": (37.3891, -5.9845),
    "cadiz": (36.5271, -6.2886),
    "barcelona": (41.3851, 2.1734),
    "lisbon": (38.7223, -9.1393),
    "lisboa": (38.7223, -9.1393),
    "valladolid": (41.6523, -4.7245),
    # Wider world
    "london": (51.5074, -0.1278),
    "paris": (48.8566, 2.3522),
    "rome": (41.9028, 12.4964),
    "roma": (41.9028, 12.4964),
    "new york": (40.7128, -74.0060),
    "washington": (38.9072, -77.0369),
    "amsterdam": (52.3676, 4.9041),
}

# Memoise resolved lookups (gazetteer + online) for the process lifetime.
_cache: dict[str, GeoPoint | None] = {}


#: Which tier resolved a name. A coordinate whose origin is unrecorded cannot
#: be checked, corrected, or curated later — and "Condoto" is ambiguous across
#: countries, so the difference between a curated gazetteer row and whatever
#: Nominatim matched first is the difference between a fact and a lead.
SOURCE_GAZETTEER = "offline gazetteer"
SOURCE_NOMINATIM = "Nominatim (OpenStreetMap)"


def geocode(
    name: str,
    *,
    online: bool = False,
    timeout: float = 5.0,
) -> GeoPoint | None:
    """Resolve a place name to a ``GeoPoint``, or ``None`` if unknown.

    Tries the offline gazetteer first. When ``online`` is set, missing names
    fall through to Nominatim. Results (including misses) are cached.
    """
    return geocode_with_source(name, online=online, timeout=timeout)[0]


def geocode_with_source(
    name: str,
    *,
    online: bool = False,
    timeout: float = 5.0,
) -> tuple[GeoPoint | None, str | None]:
    """``geocode``, plus WHICH tier resolved it (#4668).

    The point alone cannot say whether a curated row or a first Nominatim hit
    put it there, and a map pin that cannot be traced back is a number the
    reader has to take on faith. Callers that persist a coordinate must
    persist this alongside it.
    """
    key = _normalize(name)
    if not key:
        return None, None
    if key in _cache:
        cached = _cache[key]
        if cached is None:
            return None, None
        return cached, (
            SOURCE_GAZETTEER if key in _GAZETTEER else SOURCE_NOMINATIM
        )

    hit = _GAZETTEER.get(key)
    if hit is not None:
        point = GeoPoint(lat=hit[0], lon=hit[1], place_name=name.strip())
        _cache[key] = point
        return point, SOURCE_GAZETTEER

    point = _geocode_online(name, timeout=timeout) if online else None
    _cache[key] = point
    return point, (SOURCE_NOMINATIM if point is not None else None)


def geocode_places(
    names: list[str],
    *,
    online: bool = False,
    timeout: float = 5.0,
) -> dict[str, GeoPoint]:
    """Geocode many names; skip the ones that don't resolve.

    Returns ``{original_name: GeoPoint}`` preserving the caller's spelling as
    the key. Duplicate names collapse to one entry.
    """
    return {
        name: point
        for name, (point, _source) in geocode_places_with_source(
            names, online=online, timeout=timeout
        ).items()
    }


def geocode_places_with_source(
    names: list[str],
    *,
    online: bool = False,
    timeout: float = 5.0,
) -> dict[str, tuple[GeoPoint, str]]:
    """``geocode_places``, keeping each hit's resolving tier (#4668)."""
    out: dict[str, tuple[GeoPoint, str]] = {}
    for name in names:
        if not name or name in out:
            continue
        point, source = geocode_with_source(name, online=online, timeout=timeout)
        if point is not None and source is not None:
            out[name] = (point, source)
    return out


def _geocode_online(name: str, *, timeout: float) -> GeoPoint | None:
    """Single Nominatim lookup. Returns None on any error (network, parse)."""
    try:
        import httpx

        resp = httpx.get(
            _NOMINATIM_URL,
            params={"q": name, "format": "json", "limit": 1},
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout,
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            return None
        row = rows[0]
        return GeoPoint(
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            place_name=row.get("display_name") or name.strip(),
        )
    except Exception as exc:  # network down, rate-limited, bad payload
        logger.warning("Nominatim geocode failed for %r: %s", name, exc)
        return None


def _demo() -> None:
    """ponytail self-check: gazetteer hits resolve, garbage misses, bounds hold."""
    p = geocode("Popayán")
    assert p is not None and abs(p.lat - 2.4448) < 0.01, p
    assert geocode("popayan") is p, "normalization + cache should return same point"
    assert geocode("Nowhere-on-Earth-12345") is None
    assert geocode("") is None
    points = geocode_places(["Quito", "Madrid", "Quito", "???unknown???"])
    assert set(points) == {"Quito", "Madrid"}, points
    assert -90 <= points["Quito"].lat <= 90 and -180 <= points["Quito"].lon <= 180
    sourced = geocode_places_with_source(["Quito", "???unknown???"])
    assert sourced["Quito"][1] == SOURCE_GAZETTEER, sourced
    assert "???unknown???" not in sourced
    print("geo._demo OK")


if __name__ == "__main__":
    _demo()
