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


MUFI_PAGE = Path(__file__).resolve().parents[1] / "formats" / "fixtures" / "corpus" / "escriptorium_latin-mufi_clm13027-38r.alto.xml"
SIGNS_FIXTURE = FIXTURES / "mufi_clm13027-38r.signs.json"


def _stabilizer(ids: dict):
    def stable(value):
        if isinstance(value, dict):
            return {k: ("2026-09-27T12:00:00Z" if k == "created_at" and v else stable(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [stable(v) for v in value]
        return ids.get(value, value) if isinstance(value, str) else value
    return stable


def test_a_declared_sign_on_the_mufi_page_is_recorded_for_the_app(db, client):
    """`source.sign.declared`, `list-authority`, `gather-instances` (the Inspector's Signs section, 5.6):
    the app reads GET /api/signs (the project's sign list), GET /api/signs/{id}/instances (every use of
    one sign) and the inspected line's readings. Recorded on the real MUFI page (Clm 13027 fol. 38r,
    eScriptorium's ALTO), which carries U+F1AC, after a person declares the sign from a line that uses
    it -- through the calls the app makes."""
    doc_id = _import(db, MUFI_PAGE)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    from fichero_server.models import ContentRepresentation

    # The sign lives in the readings (the file's strings): the first segment on the page, top-left
    # first, whose reading uses it.
    using = {r.segment_id for r in db.all(ContentRepresentation)
             if r.document_id == doc_id and "\uf1ac" in (r.content or "")}
    line = min((s for s in body["segments"] if s["id"] in using), key=lambda s: s["anchor"]["rect"])
    declared = client.post("/api/actions/invoke", json={"name": "sign.declare", "params": {
        "name": "MUFI abbreviation sign", "picture_segment_id": line["id"], "code_point": "U+F1AC",
        "list_references": [{"authority": "MUFI", "number": "F1AC"}]}})
    assert declared.status_code == 200, declared.text
    sign_id = declared.json()["result"]["sign_id"]
    signs = client.get("/api/signs").json()
    instances = client.get(f"/api/signs/{sign_id}/instances").json()
    readings = client.get(f"/api/segments/{line['id']}/readings").json()
    assert [s["id"] for s in signs["items"]] == [sign_id]
    assert instances["total"] >= 50, instances["total"]  # the page uses it 50 times

    ids = {doc_id: "doc-mufi", line["id"]: "seg-mufi-0001", sign_id: "sign-0001"}
    # Numbered by where each segment is on the page (ids are random; places are not).
    rect_of = {s["id"]: s["anchor"]["rect"] for s in body["segments"]}
    placed = sorted(instances["items"], key=lambda i: (rect_of.get(i.get("segment_id"), [2.0]), i["count"]))
    for index, item in enumerate(placed, start=1):
        ids.setdefault(item["representation_id"], f"rep-{index:04d}")
        if item.get("segment_id"):
            ids.setdefault(item["segment_id"], f"seg-mufi-{index:04d}")
    stable = _stabilizer(ids)
    instances["items"] = placed
    recorded = {"signs": stable(signs), "instances": stable(instances), "readings": stable(readings)}
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        SIGNS_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(SIGNS_FIXTURE.read_text()) == recorded, "the app's signs fixture drifted"


LETTERFORM_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.first-mark-letterform.json"


def test_a_described_letterform_is_recorded_for_the_app(db, client):
    """`source.letterform.chain`, `features` (shown read-only inside the Signs section, 5.6, ruled
    2026-09-28 pending the maintainer): the app reads GET /api/letterforms/segment/{id}, GET
    /api/letterforms/allographs and GET /api/hands. Recorded for one letter's box on the imported
    Syriac page's first line, described as the Estrangela alaph of hand B with a wedged stem."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    line = min((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
               key=lambda s: s["anchor"]["rect"])
    x, y, w, h = line["anchor"]["rect"]

    def invoke(name, params):
        answer = client.post("/api/actions/invoke", json={"name": name, "params": params})
        assert answer.status_code == 200, answer.text
        return answer.json()["result"]

    mark_id = invoke("segment.create", {
        "document_id": doc_id, "pass_id": real["id"], "kind": "character",
        "anchor": {"document_id": doc_id, "rect": [x + w - w / 20, y, w / 20, h]},
    })["segment_ids"][0]
    allograph_id = invoke("allograph.create", {"character": "ܐ", "name": "Estrangela alaph"})["allograph_id"]
    hand_id = invoke("hand.create", {"label": "hand B"})["hand_id"]
    invoke("letterform.describe", {
        "segment_id": mark_id, "character": "ܐ", "allograph_id": allograph_id, "hand_id": hand_id,
        "features": [{"component": "stem", "feature": "wedged"}, {"component": "foot", "feature": "curved"}],
    })
    description = client.get(f"/api/letterforms/segment/{mark_id}").json()
    allographs = client.get("/api/letterforms/allographs").json()
    hands = client.get("/api/hands").json()
    assert [d["allograph_id"] for d in description["items"]] == [allograph_id]

    ids = {mark_id: "seg-mark", allograph_id: "allograph-0001", hand_id: "hand-0001"}
    for item in description["items"]:
        ids[item["id"]] = "desc-0001"
    stable = _stabilizer(ids)
    recorded = {"description": stable(description), "allographs": stable(allographs), "hands": stable(hands)}
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        LETTERFORM_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(LETTERFORM_FIXTURE.read_text()) == recorded, "the app's letterform fixture drifted"


LINKS_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.first-lines-links.json"


def test_a_link_between_two_lines_is_recorded_from_both_ends_for_the_app(db, client):
    """`source.link.typed`, `both-ways`, `source.segment.citable` (the Inspector's Links section, 5.7):
    the app reads GET /api/links/of/{id} for the inspected segment, GET /api/links/types for the Link
    menu, and GET /api/segments/{id}/reference for Copy Reference. Recorded on the imported Syriac
    page after a person says its second line CONTINUES its first -- read from each end, so the sentence
    runs the right way from each."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    first, second = sorted((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
                           key=lambda s: s["anchor"]["rect"])[:2]
    created = client.post("/api/actions/invoke", json={"name": "typed_link.create", "params": {
        "from_id": second["id"], "to_id": first["id"], "link_type": "continues", "certainty": 0.9,
        "note": "the sentence runs on"}})
    assert created.status_code == 200, created.text
    of_first = client.get(f"/api/links/of/{first['id']}").json()
    of_second = client.get(f"/api/links/of/{second['id']}").json()
    types = client.get("/api/links/types").json()
    reference = client.get(f"/api/segments/{first['id']}/reference").json()
    assert [(l["label"], l["inbound"]) for l in of_first["links"]] == [("Is continued by", True)]
    assert [(l["label"], l["inbound"]) for l in of_second["links"]] == [("Continues", False)]

    stable_route = json.loads(ROUTE_FIXTURE.read_text())
    token = {s["anchor"]["rect"].__repr__(): s["id"] for s in stable_route["segments"]}
    ids = {doc_id: stable_route["document_id"], first["id"]: token[repr(first["anchor"]["rect"])],
           second["id"]: token[repr(second["anchor"]["rect"])], of_first["links"][0]["id"]: "link-0001"}
    library_uuid = reference["reference"].split("/")[1]
    ids[reference["reference"]] = reference["reference"].replace(library_uuid, "library-0001").replace(
        doc_id, stable_route["document_id"]).replace(first["id"], ids[first["id"]])
    stable = _stabilizer(ids)
    recorded = {"of_first": stable(of_first), "of_second": stable(of_second), "types": stable(types),
                "reference": stable(reference)}
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        LINKS_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(LINKS_FIXTURE.read_text()) == recorded, "the app's links fixture drifted"


RIGHTS_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.first-line-rights.json"


def test_what_rights_apply_to_a_line_is_recorded_for_the_app(db, client):
    """`source.rights.record`, `tighten-only` (the Inspector's Rights section, 5.8): the app reads GET
    /api/rights/effective for the inspected segment -- what applies, worked out from the library down,
    with the records that added up to it. Recorded on the imported Syriac page after three records at
    three levels: a community label on the library, local models only for the page, and the first line
    restricted to one named reader -- through the calls the app makes."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    line = min((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
               key=lambda s: s["anchor"]["rect"])
    record_ids = []
    for params in (
        {"target_kind": "library", "labels": ["TK Attribution"], "holders": ["Österreichische Nationalbibliothek"]},
        {"target_kind": "document", "target_id": doc_id, "model_use": "local", "conditions": "agreement 2026-07"},
        {"target_kind": "segment", "target_id": line["id"], "restricted": True, "readers": ["owner"]},
    ):
        answer = client.post("/api/actions/invoke", json={"name": "rights.set", "params": params})
        assert answer.status_code == 200, answer.text
        record_ids.append(answer.json()["result"]["record_id"])
    effective = client.get("/api/rights/effective",
                           params={"target_kind": "segment", "target_id": line["id"]}).json()
    assert effective["restricted"] is True and effective["model_use"] == "local"
    assert [r["id"] for r in effective["records"]] == record_ids  # library first

    stable_route = json.loads(ROUTE_FIXTURE.read_text())
    token = next(s["id"] for s in stable_route["segments"]
                 if s["kind"] == "line" and s["anchor"]["rect"] == line["anchor"]["rect"])
    ids = {doc_id: stable_route["document_id"], line["id"]: token}
    for index, record_id in enumerate(record_ids, start=1):
        ids[record_id] = f"rights-{index:04d}"
    recorded = _stabilizer(ids)(effective)
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        RIGHTS_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(RIGHTS_FIXTURE.read_text()) == recorded, "the app's rights fixture drifted"


STATEMENTS_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.first-line-statements.json"


def test_what_is_said_about_a_line_is_recorded_for_the_app(db, client):
    """`source.statement.on-segment`, `both-ways` (the Inspector's 5.7, statements half): the app reads
    GET /api/segments/{id}/statements. Recorded for the imported Syriac page's first line after a claim
    is anchored to it (claim.create, then claim.patch of its anchor -- the calls the app makes) and an
    entity's supporting source names it (seeded, as an extraction would write it)."""
    from fichero_server.models.anchors import SourceAnchor
    from fichero_server.models.knowledge import EntityType, KnowledgeEntity, SourceSupport

    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    line = min((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
               key=lambda s: s["anchor"]["rect"])
    created = client.post("/api/actions/invoke", json={"name": "claim.create", "params": {
        "text": "Abraham begat Isaac", "source_document_id": doc_id, "source_excerpt": "ܐܒܪܗܡ ܐܘܠܕ"}})
    assert created.status_code == 200, created.text
    claim_id = created.json()["result"]["id"]
    patched = client.post("/api/actions/invoke", json={"name": "claim.patch", "params": {
        "claim_id": claim_id,
        "patch": {"source_anchor": {"document_id": doc_id, "segment_id": line["id"], "rect": line["anchor"]["rect"]}},
    }})
    assert patched.status_code == 200, patched.text
    entity = KnowledgeEntity(
        canonical_name="Abraham", entity_type=EntityType.person, source_document_ids=[doc_id],
        source_supports=[SourceSupport(source_document_id=doc_id, source_excerpt="ܐܒܪܗܡ",
                                       source_anchor=SourceAnchor(document_id=doc_id, segment_id=line["id"]))])
    db.save(entity)
    said = client.get(f"/api/segments/{line['id']}/statements").json()
    assert [c["claim_id"] for c in said["claims"]] == [claim_id]
    assert [m["entity_id"] for m in said["mentions"]] == [entity.id]

    stable_route = json.loads(ROUTE_FIXTURE.read_text())
    token = next(s["id"] for s in stable_route["segments"]
                 if s["kind"] == "line" and s["anchor"]["rect"] == line["anchor"]["rect"])
    recorded = _stabilizer({line["id"]: token, claim_id: "claim-0001", entity.id: "entity-0001"})(said)
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        STATEMENTS_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(STATEMENTS_FIXTURE.read_text()) == recorded, "the app's statements fixture drifted"


ORDER_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.reading-order.json"


def test_the_page_s_reading_order_is_recorded_for_the_segments_pane(db, client):
    """`source.segments-pane.exists`, `reorders` (the Segments pane, #4942): the pane lists a page's
    segments through the Order list's own calls -- GET /api/reading-orders/document/{id}, then
    GET /api/reading-orders/{order}/entries for the top level and for a region's lines. Recorded for
    the imported Syriac page, so the app's test lists, opens and reorders over the engine's answer."""
    doc_id = _import(db, SYRIAC)
    orders = client.get(f"/api/reading-orders/document/{doc_id}").json()
    order = next(o for o in orders["orders"] if o["name"] == "as-written")
    top = client.get(f"/api/reading-orders/{order['id']}/entries").json()
    assert top["entries"], "the imported page has an as-written order"
    region_entry = next(e for e in top["entries"]
                        if client.get(f"/api/reading-orders/{order['id']}/entries",
                                      params={"parent_entry_id": e["id"]}).json()["entries"])
    children = client.get(f"/api/reading-orders/{order['id']}/entries",
                          params={"parent_entry_id": region_entry["id"]}).json()

    route = client.get(f"/api/segments/document/{doc_id}").json()
    stable_route = json.loads(ROUTE_FIXTURE.read_text())
    by_rect = {repr(s["anchor"]["rect"]): s["id"] for s in stable_route["segments"]}
    ids = {doc_id: stable_route["document_id"], order["id"]: "order-0001"}
    for segment in route["segments"]:
        ids[segment["id"]] = by_rect[repr(segment["anchor"]["rect"])]
    real_pass = next(p["id"] for p in route["passes"] if not p["provisional"])
    ids[real_pass] = next(p["id"] for p in stable_route["passes"] if not p["provisional"])
    for index, entry in enumerate(top["entries"] + children["entries"], start=1):
        ids[entry["id"]] = f"entry-{index:04d}"
    for other in orders["orders"]:
        ids.setdefault(other["id"], f"order-{len(ids):04d}")
    stable = _stabilizer(ids)
    recorded = {"orders": stable(orders), "top": stable(top), "region_entry": ids[region_entry["id"]],
                "children": stable(children)}
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        ORDER_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(ORDER_FIXTURE.read_text()) == recorded, "the app's reading-order fixture drifted"


HAND_GATHER_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.everything-in-hand.json"


def test_everything_in_a_hand_is_recorded_for_the_segments_pane(db, client):
    """`source.segments-pane.gathers` (#4942): "Everything in This Hand" reads GET
    /api/hands/{id}/attributions. Recorded for the imported Syriac page after a person attributes its
    first two lines to hand B, one of them only 60% sure -- through the calls the app makes."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    first, second = sorted((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
                           key=lambda s: s["anchor"]["rect"])[:2]
    hand_id = client.post("/api/actions/invoke", json={"name": "hand.create", "params": {"label": "hand B"}}).json()["result"]["hand_id"]
    for line, certainty in ((first, 0.8), (second, 0.6)):
        answer = client.post("/api/actions/invoke", json={"name": "hand.attribute", "params": {
            "hand_id": hand_id, "segment_id": line["id"], "certainty": certainty}})
        assert answer.status_code == 200, answer.text
    everything = client.get(f"/api/hands/{hand_id}/attributions").json()
    assert sorted(a["segment_id"] for a in everything["items"]) == sorted([first["id"], second["id"]])

    stable_route = json.loads(ROUTE_FIXTURE.read_text())
    by_rect = {repr(s["anchor"]["rect"]): s["id"] for s in stable_route["segments"]}
    ids = {hand_id: "hand-0001", first["id"]: by_rect[repr(first["anchor"]["rect"])],
           second["id"]: by_rect[repr(second["anchor"]["rect"])]}
    everything["items"] = sorted(everything["items"], key=lambda a: ids[a["segment_id"]])
    for index, item in enumerate(everything["items"], start=1):
        ids[item["id"]] = f"attr-{index:04d}"
    recorded = _stabilizer(ids)(everything)
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        HAND_GATHER_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(HAND_GATHER_FIXTURE.read_text()) == recorded, "the app's everything-in-hand fixture drifted"


PICTURE_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.first-line-picture.json"


def test_a_line_s_picture_is_recorded_for_the_segments_pane(db, client):
    """`source.segments-pane.views` (the Segments pane's strip and grid, #4942): each cell reads GET
    /api/segments/{id}/picture. The corpus ships the PAGE file but not its scan, so the page image here
    is a STAND-IN at the file's own proportions (1969x2365, scaled) with every line of the file inked
    grey where the file puts it. The picture is the engine's real cut of the real first line's box.
    Recorded as base64 PNG, with the ids the route recording gives, so the app's test decodes the
    engine's own bytes."""
    import base64
    import io

    from PIL import Image, ImageDraw

    from fichero_server.actions.registry import registry
    from fichero_server.models import DocType, Document, FileType, Status
    from tests.unit.api.test_page_text_follows_the_file import BOOT

    width, height = 394, 473  # 1969x2365 scaled by 1/5
    scan = Image.new("RGB", (width, height), (250, 247, 240))
    path = Path(db.path.parent) / "syriac-stand-in.png"
    scan.save(path)
    doc = Document(name="syriac", doc_type=DocType.file, file_type=FileType.image, path=str(path),
                   status=Status.completed)
    db.save(doc)
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(SYRIAC)}, BOOT)
    body = client.get(f"/api/segments/document/{doc.id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    lines = sorted((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
                   key=lambda s: s["anchor"]["rect"])
    draw = ImageDraw.Draw(scan)
    for line in lines:
        x, y, w, h = line["anchor"]["rect"]
        draw.rectangle([x * width, y * height, (x + w) * width, (y + h) * height], fill=(90, 80, 70))
    scan.save(path)

    first = lines[0]
    picture = client.get(f"/api/segments/{first['id']}/picture", params={"size": 120})
    assert picture.status_code == 200, picture.text
    assert picture.headers["content-type"] == "image/png"
    cut = Image.open(io.BytesIO(picture.content)).convert("RGB")
    assert max(cut.size) == 120, cut.size
    assert cut.getpixel((cut.width // 2, cut.height // 2)) == (90, 80, 70), "the cut is the line, not the page"

    stable_route = json.loads(ROUTE_FIXTURE.read_text())
    token = next(s["id"] for s in stable_route["segments"]
                 if s["kind"] == "line" and s["anchor"]["rect"] == first["anchor"]["rect"])
    recorded = {"segment_id": token, "size": 120, "png_base64": base64.b64encode(picture.content).decode()}
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        PICTURE_FIXTURE.write_text(json.dumps(recorded, indent=1) + "\n")
    assert json.loads(PICTURE_FIXTURE.read_text()) == recorded, "the app's picture fixture drifted"


HISTORY_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.first-line-history.json"


def test_a_line_s_history_is_recorded_and_restoring_it_is_the_app_s_exact_call(db, client):
    """`source.segment.versioned-alone` (#5163, the Inspector's Making section at segment level): the
    app reads GET /api/segments/{id}/versions and the live row (GET /api/segments/{id}, for the version
    a restore is checked against). Recorded on the imported Syriac page's first line after two changes
    through the audited actions: moved, then its language set. Then the app's EXACT restore --
    `segment.restore_version {segment_id, version: 1, expected_version: <live>}` -- is sent: the box
    goes back, and undoing the restore by its audit id moves it again. Breaks if the history is not
    recorded per change, or if the restore the app sends is refused or restores the wrong state."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    line = min((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
               key=lambda s: s["anchor"]["rect"])
    original_rect = line["anchor"]["rect"]

    def invoke(name, params):
        answer = client.post("/api/actions/invoke", json={"name": name, "params": params})
        assert answer.status_code == 200, answer.text
        return answer.json()

    moved = dict(line["anchor"], rect=[original_rect[0] + 0.01, original_rect[1], original_rect[2], original_rect[3]])
    moved.pop("segment_id", None)
    invoke("segment.update", {"segment_id": line["id"], "expected_version": line["version"], "anchor": {
        k: moved.get(k) for k in ("document_id", "page_id", "rendition_id", "space", "rect", "polygon", "rotation",
                                  "granularity")}})
    invoke("segment.update_many", {"updates": [
        {"segment_id": line["id"], "expected_version": line["version"] + 1, "language": "syc"}]})
    versions = client.get(f"/api/segments/{line['id']}/versions").json()
    live = client.get(f"/api/segments/{line['id']}").json()
    assert [v["version"] for v in versions["items"]] == [1, 2], "one version row per change"
    assert versions["items"][0]["anchor"]["rect"] == original_rect
    assert live["segment"]["version"] == 3

    stable_route = json.loads(ROUTE_FIXTURE.read_text())
    token = next(s["id"] for s in stable_route["segments"]
                 if s["kind"] == "line" and s["anchor"]["rect"] == original_rect)
    stable_line = next(s for s in stable_route["segments"] if s["id"] == token)
    ids = {doc_id: stable_route["document_id"], line["id"]: token, real["id"]: stable_line["pass_id"],
           line["parent_segment_id"]: stable_line["parent_segment_id"]}
    for index, item in enumerate(versions["items"], start=1):
        ids[item["id"]] = f"version-{index:04d}"
        if item.get("audit_id"):
            ids[item["audit_id"]] = f"audit-{index:04d}"
    stable = _stabilizer(ids)
    recorded = {"versions": stable(versions), "live": stable(live)}
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        HISTORY_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(HISTORY_FIXTURE.read_text()) == recorded, "the app's history fixture drifted"

    # The app's exact restore, then its undo (normalized coordinates: the move was 0.01).
    restored = invoke("segment.restore_version",
                      {"segment_id": line["id"], "version": 1, "expected_version": live["segment"]["version"]})
    assert client.get(f"/api/segments/{line['id']}").json()["segment"]["anchor"]["rect"] == original_rect
    assert client.post(f"/api/actions/audit/{restored['audit_id']}/undo").status_code == 200
    assert client.get(f"/api/segments/{line['id']}").json()["segment"]["anchor"]["rect"][0] == original_rect[0] + 0.01


TABLE_PAGE = Path(__file__).resolve().parents[1] / "formats" / "fixtures" / "transkribus_abp_table_0019.page.xml"
TABLE_FIXTURE = FIXTURES / "transkribus_abp_table_0019.route.json"


def test_an_imported_table_s_cells_say_their_row_and_column_to_the_app(db, client):
    """`source.segment.table-cells` (#5168): a Transkribus table page, imported, answers the canvas's
    and the Segments pane's call (GET /api/segments/document/{id}) with every cell's row, column and
    spans exactly as its `TableCell` said -- checked against the file with lxml -- and the answer is
    recorded for the app, whose path head and row labels name a cell by its place. Breaks if a cell's
    place is lost or shifted on the way to the app."""
    doc_id = _import(db, TABLE_PAGE)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    cells = [s["cell"] for s in body["segments"] if s["pass_id"] == real["id"] and s.get("cell")]

    root = etree.parse(str(TABLE_PAGE)).getroot()
    in_file = sorted(
        (int(c.get("row")), int(c.get("col")), int(c.get("rowSpan") or 1), int(c.get("colSpan") or 1))
        for c in root.iter() if isinstance(c.tag, str) and etree.QName(c).localname == "TableCell"
    )
    assert len(in_file) == 172
    assert sorted((c["row"], c["column"], c["row_span"], c["column_span"]) for c in cells) == in_file

    # Recorded REDUCED to the table and its cells (the lines inside them are 60% of 600 KB and no part of
    # what the path head or a row label reads); reduced before stabilizing, so box indices stay whole.
    reduced = dict(body, segments=[s for s in body["segments"] if s["kind"] == "table" or s.get("cell")])
    stable = _stable(reduced)
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        TABLE_FIXTURE.write_text(json.dumps(stable, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(TABLE_FIXTURE.read_text()) == stable, "the app's table fixture drifted"


MATCHES_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.proposed-matches.json"


def test_a_page_s_proposed_matches_are_recorded_and_accept_and_reject_are_the_app_s_exact_calls(db, client):
    """`source.segment.match-record` (#5165, the Segments pane's "Proposed matches" set): the app reads
    GET /api/segments/document/{id}/matches?state=proposed. Recorded on the imported Syriac page after
    two proposals through `segment.match_propose` (the first line is the second; the third is the
    fourth, 60% sure). Then the app's EXACT verbs -- `segment.match_accept {match_id}` and
    `segment.match_reject {match_id}` -- are sent: each lands, the proposed list empties, and undoing
    the accept by its audit id makes it a proposal again. Breaks if proposals are not listed, or the
    verbs the app sends are refused or change the wrong match."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    lines = sorted((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
                   key=lambda s: s["anchor"]["rect"][1])

    def invoke(name, params):
        answer = client.post("/api/actions/invoke", json={"name": name, "params": params})
        assert answer.status_code == 200, answer.text
        return answer.json()

    first = invoke("segment.match_propose", {"from_segment_id": lines[0]["id"], "to_segment_id": lines[1]["id"]})
    second = invoke("segment.match_propose", {"from_segment_id": lines[2]["id"], "to_segment_id": lines[3]["id"],
                                              "certainty": 0.6, "note": "same words, redrawn box"})
    proposed = client.get(f"/api/segments/document/{doc_id}/matches", params={"state": "proposed"}).json()
    assert proposed["count"] == 2

    stable_route = json.loads(ROUTE_FIXTURE.read_text())

    def token_of(segment):
        return next(s["id"] for s in stable_route["segments"]
                    if s["kind"] == segment["kind"] and s["anchor"]["rect"] == segment["anchor"]["rect"])

    ids = {doc_id: stable_route["document_id"]}
    for line in lines[:4]:
        ids[line["id"]] = token_of(line)
    for index, item in enumerate(proposed["items"], start=1):
        ids[item["id"]] = f"match-{index:04d}"
    recorded = _stabilizer(ids)(proposed)
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        MATCHES_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(MATCHES_FIXTURE.read_text()) == recorded, "the app's matches fixture drifted"

    # The app's exact verbs, then the accept's undo.
    accepted = invoke("segment.match_accept", {"match_id": first["result"]["match_id"]})
    invoke("segment.match_reject", {"match_id": second["result"]["match_id"]})
    after = client.get(f"/api/segments/document/{doc_id}/matches").json()["items"]
    assert sorted(m["state"] for m in after) == ["accepted", "rejected"]
    assert client.get(f"/api/segments/document/{doc_id}/matches", params={"state": "proposed"}).json()["count"] == 0
    assert client.post(f"/api/actions/audit/{accepted['audit_id']}/undo").status_code == 200
    again = client.get(f"/api/segments/document/{doc_id}/matches", params={"state": "proposed"}).json()["items"]
    assert [m["id"] for m in again] == [first["result"]["match_id"]]
