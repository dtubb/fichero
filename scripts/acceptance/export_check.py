"""Step 3: export every imported page in its ORIGINAL format and compare it with what went in.

`GET /api/documents/{id}/export/{format}` (CLI `documents export-page` via the generated
surface, MCP `fichero_page_export`) for the pass the folder import made. The returned file
is then:

* validated with `scripts/validate_exports.py`'s own `check_bytes` (the latest schema our
  writer targets), and
* read back with `source_truth.read_truth` (plain lxml) and compared with the INPUT file:
  element counts per level and every text, exactly.

Writes ACCEPTANCE_OUT/export.json and the exported files under ACCEPTANCE_OUT/exports/.
Starts and stops its own engine.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _engine import OUT, client, engine, load, save  # noqa: E402
from source_truth import read_truth  # noqa: E402


def main() -> None:
    from validate_exports import check_bytes  # noqa: PLC0415 -- needs fichero_server on the path, set by _engine

    only = set(sys.argv[1:])
    rows = load("import.json")
    results = []
    (OUT / "exports").mkdir(parents=True, exist_ok=True)
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
                    source = staging / f"{stem}.xml"
                    if not source.exists():
                        continue
                    truth_in = read_truth(source)
                    if truth_in is None:
                        continue
                    fmt = truth_in.format
                    listing = c.request("GET", f"/api/segments/document/{page['id']}")
                    pass_ids = [p["id"] for p in listing["passes"] if p["name"] == source.name]
                    r = {"key": row["key"], "page": page["name"], "format": fmt, "pass_id": pass_ids[0] if pass_ids else None}
                    try:
                        exp = c.request(
                            "GET", f"/api/documents/{page['id']}/export/{fmt}",
                            params={"pass_id": r["pass_id"]} if r["pass_id"] else None,
                        )
                    except Exception as exc:  # noqa: BLE001 -- the refusal is the result
                        r["error"] = f"{type(exc).__name__}: {exc}"[:500]
                        results.append(r)
                        print(r["key"], r["page"], "EXPORT REFUSED", r["error"][:200], flush=True)
                        continue
                    content = exp.get("content") or ""
                    out_path = OUT / "exports" / f"{row['key']}__{stem}.{fmt}.xml"
                    out_path.write_text(content, encoding="utf-8")
                    outcome, name, problems = check_bytes(out_path.name, content.encode("utf-8"))
                    r.update(validation=outcome, validated_as=name, problems=problems[:5],
                             losses=exp.get("losses"), choices=exp.get("choices"))
                    truth_out = read_truth(out_path)
                    levels = {}
                    for level in ("region", "line", "word", "glyph"):
                        a, b = truth_in.level(level), truth_out.level(level) if truth_out else []
                        if not a and not b:
                            continue
                        texts_in = [e.text for e in a if e.text]
                        texts_out = [e.text for e in b if e.text]
                        levels[level] = {
                            "in": len(a), "out": len(b),
                            "texts_in": len(texts_in), "texts_out": len(texts_out),
                            "texts_equal_in_order": texts_in == texts_out,
                            "texts_equal_as_multiset": sorted(texts_in) == sorted(texts_out),
                            "first_difference": next(
                                ({"in": x, "out": y} for x, y in zip(texts_in, texts_out) if x != y), None
                            ),
                            "baselines_in": sum(1 for e in a if e.has_baseline),
                            "baselines_out": sum(1 for e in b if e.has_baseline),
                        }
                    r["levels"] = levels
                    results.append(r)
                    print(r["key"], r["page"], outcome, {k: (v["in"], v["out"], v["texts_equal_in_order"], v["texts_equal_as_multiset"]) for k, v in levels.items()}, flush=True)
                    save("export.json", results)
    save("export.json", results)


if __name__ == "__main__":
    main()
