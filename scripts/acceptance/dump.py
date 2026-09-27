"""Dump what the engine says about the imported pages, for looking at by hand.

    dump.py            every imported page: its segments (per-document route), one
                       segment's detail, the page's derived text, its reading orders
Writes ACCEPTANCE_OUT/dump/<key>__<page>.json. Starts and stops its own engine.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _engine import client, engine, load, save  # noqa: E402


def safe(c, method, path, **kw):
    try:
        return c.request(method, path, **kw)
    except Exception as exc:  # noqa: BLE001 -- a refusal is data here
        return {"__error__": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    only = set(sys.argv[1:])
    rows = load("import.json")
    with engine():
        with client() as c:
            for row in rows:
                if only and row["key"] not in only:
                    continue
                for page in row["pages"]:
                    if not page.get("image"):
                        continue
                    doc_id = page["id"]
                    segs = safe(c, "GET", f"/api/segments/document/{doc_id}")
                    first = (segs.get("segments") or [{}])[0].get("id") if isinstance(segs, dict) else None
                    out = {
                        "document": safe(c, "GET", f"/api/documents/{doc_id}"),
                        "segments": segs,
                        "segment_detail": safe(c, "GET", f"/api/segments/{first}") if first else None,
                        "readings_of_first": safe(c, "GET", f"/api/segments/{first}/readings") if first else None,
                        "text": safe(c, "GET", f"/api/segments/document/{doc_id}/text"),
                        "reading_orders": safe(c, "GET", f"/api/reading-orders/document/{doc_id}"),
                    }
                    save(f"dump/{row['key']}__{Path(page['name']).stem}.json", out)
                    print(row["key"], page["name"], "segments:", len(segs.get("segments", [])) if isinstance(segs, dict) else segs)


if __name__ == "__main__":
    main()
