"""Step 2: read every imported page back at every level and compare it with the source file.

Expected side: `source_truth.read_truth` (plain lxml over the staged PAGE / ALTO file, not
the engine's readers). Engine side, only through the public surface the CLI and MCP use:

    GET /api/segments/document/{id}        (CLI `segments list-document`, MCP `fichero_segments`)
    GET /api/segments/{id}/readings        (CLI `segments list-readings`; no MCP tool)
    GET /api/segments/document/{id}/text   (CLI `segments get-document-text`; no MCP tool)
    GET /api/reading-orders/document/{id}  (CLI `reading-orders ...`; no MCP tool)
    GET /api/segments/{id}                 (CLI `segments get`, MCP `fichero_segment`)

Segments are matched to source elements by level and position (the engine keeps no
source element id; see the report). For each level it checks: the count, the exact text of
every segment (Python `==` on the str, so byte for byte after UTF-8: RTL, combining marks and
MUFI private-use characters included), language / script / direction where the source
states them, polygon and baseline survival, nesting where the engine exposes a parent, and
the stated reading order.

Writes ACCEPTANCE_OUT/readback.json. Starts and stops its own engine.
"""

from __future__ import annotations

import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _engine import OUT, client, engine, load, save  # noqa: E402
from source_truth import read_truth  # noqa: E402

LEVEL_OF_KIND = {"region": "region", "table": "region", "line": "line", "word": "word", "glyph": "glyph", "character": "glyph"}


def reading_text(readings: dict) -> str | None:
    items = readings.get("items") or []
    chosen = [r for r in items if r.get("chosen")] or items
    for r in chosen:
        for key in ("text", "content", "value"):
            if isinstance(r.get(key), str):
                return r[key]
    return None


def has_pua(s: str | None) -> bool:
    return bool(s) and any(0xE000 <= ord(ch) <= 0xF8FF for ch in s)


def has_combining(s: str | None) -> bool:
    return bool(s) and any(unicodedata.combining(ch) for ch in s)


def has_rtl(s: str | None) -> bool:
    return bool(s) and any(unicodedata.bidirectional(ch) in ("R", "AL") for ch in s)


def compare_page(c, key: str, page: dict, source: Path, raw_samples: dict) -> dict:
    truth = read_truth(source)
    listing = c.request("GET", f"/api/segments/document/{page['id']}")
    passes = [p for p in listing["passes"] if not p.get("provisional")]
    # The folder import's pass is the one named after the layout file.
    pass_ids = [p["id"] for p in passes if p["name"] == source.name] or [p["id"] for p in passes[:1]]
    segs = [s for s in listing["segments"] if s["pass_id"] in pass_ids]
    by_level: dict[str, list[dict]] = {}
    for s in segs:
        by_level.setdefault(LEVEL_OF_KIND.get(s["kind"], s["kind"]), []).append(s)

    out: dict = {"key": key, "page": page["name"], "document_id": page["id"], "source": source.name,
                 "format": truth.format if truth else None, "units": truth.units if truth else None,
                 "engine_kinds": dict(Counter(s["kind"] for s in segs)), "levels": {}}
    if truth is None:
        return out

    for level in ("region", "line", "word", "glyph"):
        expected = truth.level(level)
        got = by_level.get(level, [])
        if not expected and not got:
            continue
        row: dict = {"expected": len(expected), "got": len(got)}
        texts_expected = [e for e in expected if e.text is not None]
        mismatches = []
        text_checked = 0
        features = Counter()
        for e, s in zip(expected, got):
            if e.text is None:
                continue
            readings = c.request("GET", f"/api/segments/{s['id']}/readings")
            if level not in raw_samples:
                raw_samples[level] = {"segment": s, "readings": readings}
            text = reading_text(readings)
            text_checked += 1
            features["pua"] += has_pua(e.text)
            features["combining"] += has_combining(e.text)
            features["rtl"] += has_rtl(e.text)
            # An empty source TextEquiv and no reading are the same statement.
            if text != e.text and not (e.text == "" and text is None):
                mismatches.append({"source_id": e.id, "expected": e.text, "got": text,
                                   "nfc_equal": text is not None and unicodedata.normalize("NFC", text) == unicodedata.normalize("NFC", e.text)})
        row["text_expected"] = len(texts_expected)
        row["text_checked"] = text_checked
        row["text_exact"] = text_checked - len(mismatches)
        row["text_mismatches"] = mismatches[:5]
        row["text_mismatch_count"] = len(mismatches)
        row["source_features"] = dict(features)
        row["polygons_expected"] = sum(1 for e in expected if e.polygon_points >= 3)
        row["polygons_got"] = sum(1 for s in got if s["anchor"].get("polygon"))
        row["baselines_expected"] = sum(1 for e in expected if e.has_baseline)
        row["baselines_got"] = sum(1 for s in got if s.get("baseline"))
        row["language_expected"] = dict(Counter(e.language for e in expected if e.language))
        row["language_got"] = dict(Counter(s["language"] for s in got if s.get("language")))
        row["direction_expected"] = dict(Counter(e.direction for e in expected if e.direction))
        row["direction_got"] = dict(Counter(s["direction"] for s in got if s.get("direction")))
        row["script_expected"] = dict(Counter(e.script for e in expected if e.script))
        row["script_got"] = dict(Counter(s["script"] for s in got if s.get("script")))
        row["custom_expected"] = sum(1 for e in expected if e.custom)
        row["custom_kept"] = sum(1 for s in got if (s.get("metadata") or {}).get("foreign", {}).get("custom"))
        out["levels"][level] = row

    # Nesting: the only parent the public surface exposes is the text route's
    # block -> region_segment_id (lines under their region).
    text = c.request("GET", f"/api/segments/document/{page['id']}/text")
    out["text_route"] = {k: text.get(k) for k in ("pass_id", "pass_basis", "kind", "order", "omitted")}
    out["block_directions"] = dict(Counter(b.get("direction") for b in text.get("blocks") or []))
    detail = c.request("GET", f"/api/segments/{segs[1]['id']}") if len(segs) > 1 else {}
    out["detail_has_parent"] = "parent_segment_id" in (detail.get("segment") or {})
    seg_region: dict[str, str] = {}
    for b in text.get("blocks") or []:
        for sp in b.get("spans") or []:
            seg_region[sp["segment_id"]] = b.get("region_segment_id")
    parent_of = {e.id: e.parent for e in truth.elements}
    level_of = {e.id: e.level for e in truth.elements}

    def region_ancestor(src_id):
        cur = parent_of.get(src_id)
        while cur is not None and level_of.get(cur) != "region":
            cur = parent_of.get(cur)
        return cur

    region_map = dict(zip([s["id"] for s in by_level.get("region", [])], [e.id for e in truth.level("region")]))
    nesting = {}
    for level in ("line", "word", "glyph"):
        ok = checked = 0
        for e, s in zip(truth.level(level), by_level.get(level, [])):
            if s["id"] in seg_region:
                checked += 1
                ok += region_map.get(seg_region[s["id"]]) == region_ancestor(e.id)
        if checked:
            nesting[level] = {"checked": checked, "ok": ok}
    out["nesting_in_regions"] = nesting

    # Order: the derived page text's spans, each mapped back to its source element's
    # position in the file. With no ReadingOrder in the file, the file's own order is the
    # order as written; a span whose source index goes BACKWARDS is out of that order.
    src_index: dict[str, int] = {}
    for level in ("region", "line", "word", "glyph"):
        for e, s in zip(truth.level(level), by_level.get(level, [])):
            src_index[s["id"]] = truth.elements.index(e)
    seq = [src_index[sp["segment_id"]] for b in text.get("blocks") or [] for sp in b.get("spans") or [] if sp["segment_id"] in src_index]
    out["text_order"] = {
        "spans": len(seq),
        "backward_steps": sum(1 for a, b in zip(seq, seq[1:]) if b < a),
        "blocks": len(text.get("blocks") or []),
        "file_has_reading_order": bool(truth.reading_order),
    }

    orders = c.request("GET", f"/api/reading-orders/document/{page['id']}")
    out["reading_orders"] = [{"name": o["name"], "kind": o["kind"], "entries": o.get("entry_count")} for o in orders.get("orders", [])]
    out["reading_order_source"] = len(truth.reading_order)
    return out


def main() -> None:
    only = set(sys.argv[1:])
    rows = load("import.json")
    results = []
    raw_samples: dict = {}
    with engine():
        with client() as c:
            for row in rows:
                if only and row["key"] not in only:
                    continue
                staging = OUT / "staging" / row["key"]
                for page in row["pages"]:
                    if not page.get("image"):
                        continue
                    stem = Path(page["name"]).stem
                    source = next((p for p in sorted(staging.glob(f"{stem}.xml"))), None)
                    if source is None:
                        continue
                    r = compare_page(c, row["key"], page, source, raw_samples)
                    results.append(r)
                    print(r["key"], r["page"], {lvl: (v["expected"], v["got"], v.get("text_exact"), v.get("text_mismatch_count")) for lvl, v in r["levels"].items()}, flush=True)
                    save("readback.json", results)
    save("readback_raw_samples.json", raw_samples)


if __name__ == "__main__":
    main()
