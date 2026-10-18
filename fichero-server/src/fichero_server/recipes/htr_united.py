"""HTR-United's catalogue: ground-truth datasets by language, script and hand (`source.find.htr-united-and-tessdata`,
#5571). A dataset is offered as a bake-off test set or as training data, with its licence, size and format shown; it is
never a reader and never the rules' choice. Kept in the model store's `discovery/` folder like the other listings."""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CATALOG_URL = "https://raw.githubusercontent.com/HTR-United/htr-united/master/catalog.json"
CATALOG_FILE = "htr-united.json"
#: `script-type` values whose pages are print; the rest hold some handwriting.
_PRINT_ONLY = frozenset({"only-typed", "mainly-typed"})


def _store_root() -> Path:
    from fichero_server.recipes.discovery import _store_root as root

    return root()


def _harvest() -> dict[str, dict[str, Any]]:
    """The catalogue as GitHub serves it, {id: entry}. The one network boundary here; tests replace it."""
    with urllib.request.urlopen(CATALOG_URL, timeout=30) as response:  # noqa: S310 (a fixed https URL)
        return json.load(response)


def _tags(codes: list[str]) -> list[str]:
    from fichero_server.recipes.names import _language_tags

    tags = _language_tags()
    return [tags.get(code.lower(), code.lower()) for code in codes]


def _count(entry: dict[str, Any], metric: str) -> int | None:
    for item in entry.get("volume") or []:
        if item.get("metric") == metric and isinstance(item.get("count"), int):
            return item["count"]
    return None


def rows(catalog: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The catalogue's datasets as discovery keeps them, in the catalogue's order. A catalogue that is not an
    object of objects raises ValueError (the finder says it could not be read and keeps the last one)."""
    if not isinstance(catalog, dict) or not all(isinstance(e, dict) for e in catalog.values()):
        raise ValueError("HTR-United's catalogue is not a list of datasets by id")
    out = []
    for entry in catalog.values():
        if not all(isinstance(entry.get(k) or [], list) for k in ("language", "script", "volume")):
            raise ValueError(f"HTR-United's dataset {entry.get('title')!r} lists its languages or scripts wrongly")
        licence = entry.get("license")
        licence = licence[0] if isinstance(licence, list) and licence else licence
        out.append({
            "title": str(entry.get("title") or ""),
            "url": str(entry.get("url") or ""),
            "description": str(entry.get("description") or "").strip(),
            "languages": _tags([str(c) for c in entry.get("language") or []]),
            "scripts": [str(s["iso"]) for s in entry.get("script") or [] if isinstance(s, dict) and s.get("iso")],
            "handwriting": entry.get("script-type") not in _PRINT_ONLY,
            "format": str(entry.get("format") or ""),
            "licence": ({"name": str(licence.get("name") or ""), "url": str(licence.get("url") or "")}
                        if isinstance(licence, dict) else {"name": str(licence or ""), "url": ""}),
            "lines": _count(entry, "lines"), "pages": _count(entry, "pages"),
        })
    return out


def matching(datasets: list[dict[str, Any]], *, languages: frozenset[str], scripts: frozenset[str],
             handwriting: bool | None = None) -> list[dict[str, Any]]:
    """The datasets in any of these languages (and, when scripts are given, one of the scripts), most lines first."""
    found = [d for d in datasets
             if set(d["languages"]) & languages
             and (not scripts or not d["scripts"] or set(d["scripts"]) & scripts)
             and (handwriting is None or d["handwriting"] == handwriting)]
    return sorted(found, key=lambda d: d["lines"] or 0, reverse=True)


#: Licences used without asking: open, attribution at most. Anything else, or none stated, is accepted first.
_OPEN = frozenset({"cc0-1.0", "cc-by-4.0", "cc-by-sa-4.0", "cc-by-3.0", "cc-by-sa-3.0", "mit", "apache-2.0",
                   "etalab-2.0", "odbl-1.0", "odc-by"})
_IMPORTABLE = ("page", "alto")


def offered(datasets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each dataset with what it may be used as (`as`: test-set, training) and whether Fichero can import it.
    A licence outside `_OPEN` leaves `as` empty and `accept` says what to accept first (ground truth only, licence
    respected: nothing is used unaccepted)."""
    from fichero_server.recipes.assemble import _licence_words

    out = []
    for d in datasets:
        name = (d["licence"].get("name") or "").strip()
        open_ = name.lower() in _OPEN
        out.append({**d, "as": ["test-set", "training"] if open_ else [],
                    "accept": None if open_ else _licence_words(name),
                    "importable": any(k in d["format"].lower() for k in _IMPORTABLE)})
    return out


def cached() -> dict[str, Any] | None:
    """The listing kept from the last fetch ({"fetched_at", "records"}), or None. Never the network."""
    try:
        data = json.loads((_store_root() / CATALOG_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("records"), list) else None


def refresh() -> dict[str, Any]:
    """Fetch the catalogue and keep it. Network: call only behind the egress check."""
    data = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "records": rows(_harvest())}
    folder = _store_root()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".{CATALOG_FILE}.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(folder / CATALOG_FILE)
    return data
