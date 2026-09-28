"""An imported page draws its boxes on the image (#5146).

The maintainer opened an imported Syriac page: its text showed, the image had NO boxes. The engine
half was right -- this pins it -- and the app dropped the page's only pass for having no artifact
type. So the end-to-end test is split at the wire, and the wire is recorded:

1. here: `format.import` of the real PAGE file, then the EXACT call the canvas's store makes
   (`GET /api/segments/document/{id}`), checked against the file itself with lxml;
2. the answer is recorded, ids and times made stable, as a fixture the app's test plays back
   through the SAME `SegmentStore.load` -> `SegmentDisplay.selected(for:store:)` the canvas calls
   (`ImportedPageDrawsItsBoxesTests.swift`), over a stubbed HTTP transport and nothing else.

The fixture is compared here on every run, so it cannot drift from what the engine answers.
Rewrite it with FICHERO_UPDATE_FIXTURES=1.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from tests.unit.api.test_page_text_follows_the_file import SYRIAC, _import

REPO = next(p for p in Path(__file__).resolve().parents if (p / "fichero" / "Tests").is_dir())
FIXTURES = REPO / "fichero" / "Tests" / "Fixtures" / "segments"
ROUTE_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.route.json"
EXPECTED_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.expected-boxes.json"
_KIND = {"TextRegion": "region", "TextLine": "line"}


def _file_boxes(path: Path) -> list[dict]:
    """Every region and line of the PAGE file, as the canvas should draw it: level + normalized box."""
    tree = etree.parse(str(path))
    ns = {"p": tree.getroot().nsmap[None]}
    page = tree.find(".//p:Page", ns)
    width, height = float(page.get("imageWidth")), float(page.get("imageHeight"))
    boxes = []
    for element in tree.iter():
        kind = _KIND.get(etree.QName(element).localname)
        coords = element.find("p:Coords", ns) if kind else None
        if coords is None:
            continue
        points = [tuple(map(float, pair.split(","))) for pair in coords.get("points").split()]
        xs, ys = [x for x, _ in points], [y for _, y in points]
        boxes.append({"level": kind, "bbox": [
            round(min(xs) / width, 6), round(min(ys) / height, 6),
            round((max(xs) - min(xs)) / width, 6), round((max(ys) - min(ys)) / height, 6),
        ]})
    return sorted(boxes, key=lambda b: (b["level"], b["bbox"]))


def _stable(body: dict) -> dict:
    """The route's answer with random ids and wall-clock times replaced by stable ones, and the
    segments in a stable order (box_index renumbered to match, per pass) -- same meaning, same bytes."""
    tokens: dict[str, str] = {}

    def token(value, prefix):
        if value is None:
            return None
        return tokens.setdefault(value, f"{prefix}-{len(tokens) + 1:04d}")

    segments = sorted(body["segments"], key=lambda s: (s["pass_id"], s["kind"], s["anchor"].get("rect") or []))
    token(body["document_id"], "doc")
    for p in body["passes"]:
        token(p["id"], "pass")
    for s in segments:
        token(s["id"], "seg")
    per_pass: dict[str, int] = {}
    out_segments = []
    for s in segments:
        s = json.loads(json.dumps(s))
        s["id"], s["pass_id"] = tokens[s["id"]], tokens[s["pass_id"]]
        s["document_id"] = tokens[s["document_id"]]
        s["parent_segment_id"] = token(s.get("parent_segment_id"), "seg")
        s["anchor"]["document_id"] = tokens.get(s["anchor"].get("document_id"), s["anchor"].get("document_id"))
        s["box_index"] = per_pass.setdefault(s["pass_id"], 0)
        per_pass[s["pass_id"]] += 1
        out_segments.append(s)
    passes = []
    for p in body["passes"]:
        p = dict(p, id=tokens[p["id"]], document_id=tokens[p["document_id"]])
        if p.get("created_at"):
            p["created_at"] = "2026-09-27T12:00:00Z"
        passes.append(p)
    return {"document_id": tokens[body["document_id"]], "passes": passes, "segments": out_segments}


def test_an_imported_page_s_segments_reach_the_canvas_s_call_as_the_file_s_regions_and_lines(db, client):
    doc_id = _import(db, SYRIAC)
    response = client.get(f"/api/segments/document/{doc_id}")      # SegmentStore.load's call
    assert response.status_code == 200, response.text
    body = response.json()

    real = [p for p in body["passes"] if not p["provisional"]]
    assert len(real) == 1, body["passes"]
    # The input the app must accept: a pass with NO artifact behind it (#5146).
    assert real[0]["artifact_type"] is None and real[0]["source_artifact_id"] is None
    mine = [s for s in body["segments"] if s["pass_id"] == real[0]["id"]]
    assert sorted(s["box_index"] for s in mine) == list(range(len(mine)))   # geometry(from:)'s precondition

    drawn = sorted(
        ({"level": s["kind"], "bbox": [round(v, 6) for v in s["anchor"]["rect"]]} for s in mine),
        key=lambda b: (b["level"], b["bbox"]),
    )
    expected = _file_boxes(SYRIAC)
    assert len(expected) == 16
    assert drawn == expected

    stable = _stable(body)
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        FIXTURES.mkdir(parents=True, exist_ok=True)
        ROUTE_FIXTURE.write_text(json.dumps(stable, indent=1, ensure_ascii=True) + "\n")
        EXPECTED_FIXTURE.write_text(json.dumps(expected, indent=1) + "\n")
    assert json.loads(ROUTE_FIXTURE.read_text()) == stable, "the app's fixture drifted from the engine's answer"
    assert json.loads(EXPECTED_FIXTURE.read_text()) == expected
