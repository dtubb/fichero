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


READINGS_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.first-line-readings.json"


def test_a_line_s_readings_with_a_correction_are_recorded_for_the_app(db, client):
    """#5153 (choose which reading counts): the app's Text section reads GET
    /api/segments/{id}/readings. Recorded here for the first line of the imported Syriac page after a
    person's correction -- which COUNTS, basis "correction" (#5175: a correction outranks the reading it
    corrects) -- through the calls the app makes, so the app's test shows why it counts and can choose
    the file's reading back over the engine's own answer."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    line = min((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
               key=lambda s: s["anchor"]["rect"])
    before = client.get(f"/api/segments/{line['id']}/readings").json()
    assert before["count"] == 1
    file_reading = before["items"][0]
    corrected = client.post("/api/actions/invoke", json={"name": "representation.create", "params": {
        "document_id": doc_id, "segment_id": line["id"], "kind": "transcription",
        "content": file_reading["content"] + " (corrected)",
        "corrects_representation_id": file_reading["id"],
    }})
    assert corrected.status_code == 200, corrected.text
    after = client.get(f"/api/segments/{line['id']}/readings").json()
    assert after["count"] == 2
    counting = after["counting"]["transcription"]
    # The person's correction counts over the file's reading it corrects (#5175); choosing the file's
    # reading back is what the Text section's "Make This Count" is for.
    correction = next(i for i in after["items"] if i["corrects_representation_id"] == file_reading["id"])
    assert counting["representation_id"] == correction["id"] and counting["basis"] == "correction"

    # Stable ids, the SAME tokens the route recording gives this segment and page.
    stable_route = json.loads(ROUTE_FIXTURE.read_text())
    token = next(s["id"] for s in stable_route["segments"]
                 if s["kind"] == "line" and s["anchor"]["rect"] == line["anchor"]["rect"])
    ids = {doc_id: stable_route["document_id"], line["id"]: token}
    for index, item in enumerate(sorted(after["items"], key=lambda i: i["created_at"]), start=1):
        ids[item["id"]] = f"rep-{index:04d}"

    def stable(value):
        if isinstance(value, dict):
            return {k: ("2026-09-27T12:00:00Z" if k == "created_at" and v else stable(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [stable(v) for v in value]
        return ids.get(value, value) if isinstance(value, str) else value

    recorded = stable(after)
    recorded["counting"] = {k: stable(v) for k, v in after["counting"].items()}
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        READINGS_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(READINGS_FIXTURE.read_text()) == recorded, "the app's readings fixture drifted"


SETTINGS_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.first-line-settings.json"


def test_a_line_s_resolved_language_script_and_direction_are_recorded_for_the_app(db, client):
    """#5158 (the Inspector's Language & script section): the app reads GET
    /api/source-settings/resolve?segment_id= for the selection -- each fact with the rung that
    answered (source.lang.says-where-from). Recorded for the imported Syriac page's first line."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    line = min((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
               key=lambda s: s["anchor"]["rect"])
    resolved = client.get("/api/source-settings/resolve", params={"segment_id": line["id"]})
    assert resolved.status_code == 200, resolved.text
    answer = resolved.json()
    keys = [s["key"] for s in answer["settings"]]
    assert {"language", "script", "direction"} <= set(keys)

    stable_route = json.loads(ROUTE_FIXTURE.read_text())
    token = next(s["id"] for s in stable_route["segments"]
                 if s["kind"] == "line" and s["anchor"]["rect"] == line["anchor"]["rect"])
    recorded = dict(answer, document_id=stable_route["document_id"], segment_id=token)
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        SETTINGS_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(SETTINGS_FIXTURE.read_text()) == recorded, "the app's settings fixture drifted"


HANDS_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.first-line-hands.json"


def test_a_line_s_hand_attribution_is_recorded_for_the_app(db, client):
    """#5161 (the Inspector's Hands section): the app reads GET /api/hands (the project's hands) and
    GET /api/hands/segment/{id} (who wrote this segment's ink, and who judged so). Recorded for the
    imported Syriac page's first line after a person names hand B and attributes the line to it --
    through the calls the app makes (POST /api/actions/invoke)."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    line = min((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
               key=lambda s: s["anchor"]["rect"])
    created = client.post("/api/actions/invoke", json={"name": "hand.create", "params": {
        "label": "hand B", "style": "Estrangela"}})
    assert created.status_code == 200, created.text
    hand_id = created.json()["result"]["hand_id"]
    attributed = client.post("/api/actions/invoke", json={"name": "hand.attribute", "params": {
        "hand_id": hand_id, "segment_id": line["id"], "certainty": 0.8}})
    assert attributed.status_code == 200, attributed.text
    hands = client.get("/api/hands").json()
    of_line = client.get(f"/api/hands/segment/{line['id']}").json()
    assert [a["hand_id"] for a in of_line["items"]] == [hand_id]

    stable_route = json.loads(ROUTE_FIXTURE.read_text())
    token = next(s["id"] for s in stable_route["segments"]
                 if s["kind"] == "line" and s["anchor"]["rect"] == line["anchor"]["rect"])
    ids = {line["id"]: token, hand_id: "hand-0001"}
    for index, item in enumerate(of_line["items"], start=1):
        ids[item["id"]] = f"attr-{index:04d}"

    def stable(value):
        if isinstance(value, dict):
            return {k: ("2026-09-27T12:00:00Z" if k == "created_at" and v else stable(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [stable(v) for v in value]
        return ids.get(value, value) if isinstance(value, str) else value

    recorded = {"hands": stable(hands), "attributions": stable(of_line)}
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        HANDS_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(HANDS_FIXTURE.read_text()) == recorded, "the app's hands fixture drifted"


EDITORIAL_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.first-line-editorial.json"


def test_a_line_s_editorial_facts_are_recorded_for_the_app(db, client):
    """`source.sure.editorial-facts` / `brackets-are-drawn` (the Inspector's Certainty and Damage
    section): the app reads GET /api/editorial/segment/{id} -- the facts about the line and its counting
    reading as the editor prints it. Recorded for the imported Syriac page's first line after a person
    says its first three letters are unclear (faded) and a lost stretch of two letters stands after the
    fifth -- through the calls the app makes (POST /api/actions/invoke)."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    line = min((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
               key=lambda s: s["anchor"]["rect"])
    [reading] = client.get(f"/api/segments/{line['id']}/readings").json()["items"]
    for params in (
        {"kind": "unclear", "char_start": 0, "char_end": 3, "reason": "faded", "certainty": 0.8},
        {"kind": "lost", "char_start": 5, "extent_quantity": 2, "extent_unit": "character", "reason": "a hole"},
    ):
        recorded_fact = client.post("/api/actions/invoke", json={"name": "editorial.record", "params": {
            "segment_id": line["id"], "representation_id": reading["id"], **params}})
        assert recorded_fact.status_code == 200, recorded_fact.text
    answer = client.get(f"/api/editorial/segment/{line['id']}").json()
    text = reading["content"]
    assert answer["drawn"] == "".join(c + "̣" for c in text[:3]) + text[3:5] + "[.2]" + text[5:]
    assert answer["drawn_from"] == reading["id"]

    stable_route = json.loads(ROUTE_FIXTURE.read_text())
    token = next(s["id"] for s in stable_route["segments"]
                 if s["kind"] == "line" and s["anchor"]["rect"] == line["anchor"]["rect"])
    ids = {line["id"]: token, reading["id"]: "rep-0001"}
    for index, item in enumerate(answer["items"], start=1):
        ids[item["id"]] = f"fact-{index:04d}"

    def stable(value):
        if isinstance(value, dict):
            return {k: ("2026-09-27T12:00:00Z" if k == "created_at" and v else stable(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [stable(v) for v in value]
        return ids.get(value, value) if isinstance(value, str) else value

    recorded = stable(answer)
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        EDITORIAL_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(EDITORIAL_FIXTURE.read_text()) == recorded, "the app's editorial fixture drifted"
