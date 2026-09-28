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
    # A restriction names ACCOUNTS by id, and must name whoever sets it (#4953's enforcement refuses one
    # that would lock its setter out); the owner's id is recorded as "owner", as before.
    from fichero_server.security import authz
    owner_id = authz.resolve_user("owner").id
    for params in (
        {"target_kind": "library", "labels": ["TK Attribution"], "holders": ["Österreichische Nationalbibliothek"]},
        {"target_kind": "document", "target_id": doc_id, "model_use": "local", "conditions": "agreement 2026-07"},
        {"target_kind": "segment", "target_id": line["id"], "restricted": True, "readers": [owner_id]},
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
    ids = {doc_id: stable_route["document_id"], line["id"]: token, owner_id: "owner"}
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


FLOW_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.named-orders-and-flow.json"


def test_a_named_order_and_a_flow_onto_the_next_page_are_recorded_for_the_order_picker(db, client):
    """`source.order.named-multiple`, `source.order.next-previous`, `source.segment.flow` (#5160, the
    Order list's picker): on the imported Syriac page, the app's EXACT creates -- `reading_order.create
    {document_id, pass_id, name, kind, seed_from_pass: true}` for a named order and for a flow -- then a
    second imported page's first line placed at the flow's end. Recorded: the page's orders (as-written
    first, then by name), the flow's top level, what reads after the flow's last entry on this page (the
    next page's line: the neighbours route), and that line's own read (the page Next opens). Breaks if
    a created order is not listed, the flow does not cross the page, or neighbours answer wrongly."""
    doc_id = _import(db, SYRIAC)
    next_page = _import(db, SYRIAC)
    route = client.get(f"/api/segments/document/{doc_id}").json()
    real_pass = next(p["id"] for p in route["passes"] if not p["provisional"])

    def invoke(name, params):
        answer = client.post("/api/actions/invoke", json={"name": name, "params": params})
        assert answer.status_code == 200, answer.text
        return answer.json()["result"]

    named = invoke("reading_order.create", {"document_id": doc_id, "pass_id": real_pass, "name": "Commentary order",
                                            "kind": "imposed", "seed_from_pass": True})
    flow = invoke("reading_order.create", {"document_id": doc_id, "pass_id": real_pass, "name": "Into the next page",
                                           "kind": "flow", "seed_from_pass": True})
    other = client.get(f"/api/segments/document/{next_page}").json()
    other_pass = next(p["id"] for p in other["passes"] if not p["provisional"])
    other_line = min((s for s in other["segments"] if s["pass_id"] == other_pass and s["kind"] == "line"),
                     key=lambda s: s["anchor"]["rect"])
    placed = client.post(f"/api/reading-orders/{flow['order_id']}/place",
                         json={"segment_id": other_line["id"], "at_end": True})
    assert placed.status_code == 200, placed.text

    orders = client.get(f"/api/reading-orders/document/{doc_id}").json()
    assert [o["name"] for o in orders["orders"]][0] == "as-written"
    assert {o["id"] for o in orders["orders"]} >= {named["order_id"], flow["order_id"]}
    top = client.get(f"/api/reading-orders/{flow['order_id']}/entries").json()
    last_here = top["entries"][-2]["segment_id"]
    assert top["entries"][-1]["segment_id"] == other_line["id"]
    neighbours = client.get(f"/api/reading-orders/{flow['order_id']}/neighbours",
                            params={"segment_id": last_here}).json()
    assert neighbours["next_segment_id"] == other_line["id"], "the flow crosses onto the next page"
    across = client.get(f"/api/segments/{other_line['id']}").json()
    assert across["segment"]["document_id"] == next_page

    stable_route = json.loads(ROUTE_FIXTURE.read_text())
    by_rect = {repr(s["anchor"]["rect"]): s["id"] for s in stable_route["segments"]}
    ids = {doc_id: stable_route["document_id"], next_page: "doc-0002", other_line["id"]: "seg-next-0001",
           real_pass: next(p["id"] for p in stable_route["passes"] if not p["provisional"]), other_pass: "pass-next"}
    for segment in route["segments"]:
        ids[segment["id"]] = by_rect[repr(segment["anchor"]["rect"])]
    for other_segment in other["segments"]:
        ids.setdefault(other_segment["id"], f"seg-next-{len(ids):04d}")
    for index, order in enumerate(orders["orders"], start=1):
        ids[order["id"]] = f"order-{index:04d}"
    for index, entry in enumerate(top["entries"], start=1):
        ids[entry["id"]] = f"entry-{index:04d}"
    stable = _stabilizer(ids)
    recorded = {"orders": stable(orders), "flow_top": stable(top), "neighbours": stable(neighbours),
                "across": stable(across)}
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        FLOW_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(FLOW_FIXTURE.read_text()) == recorded, "the app's orders-and-flow fixture drifted"


RESOLVE_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.reference-resolved.json"


def test_a_citable_reference_resolves_to_its_page_and_follows_a_merge_for_the_url_handler(db, client):
    """`source.segment.citable` (#5164, the app's `fichero:segment/…` URL handler): the engine's own
    reference for the imported Syriac page's first line (GET /api/segments/{id}/reference) is sent
    WHOLE to POST /api/locations/resolve -- the handler's exact call -- and names the page and the
    line. Then the line is joined into the next one (`segment.merge`, keeping the next), and the SAME
    reference resolves to the live line that absorbed it: an old link still opens the right place.
    Both answers are recorded for the app. Breaks if the resolver does not accept the string form, or
    an old reference to a merged line opens nothing or the wrong line."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    lines = sorted((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
                   key=lambda s: s["anchor"]["rect"][1])
    first, second = lines[0], lines[1]
    reference = client.get(f"/api/segments/{first['id']}/reference").json()["reference"]
    assert reference.startswith("fichero:segment/") and reference.endswith(f"/{doc_id}/{first['id']}")

    direct = client.post("/api/locations/resolve", json={"segmentId": reference})
    assert direct.status_code == 200, direct.text
    assert direct.json()["resolvedDocumentId"] == doc_id and direct.json()["resolvedSegmentId"] == first["id"]

    merged = client.post("/api/actions/invoke", json={"name": "segment.merge", "params": {
        "segment_ids": [second["id"], first["id"]], "keep_id": second["id"],
        "expected_versions": {second["id"]: second["version"], first["id"]: first["version"]}}})
    assert merged.status_code == 200, merged.text
    followed = client.post("/api/locations/resolve", json={"segmentId": reference})
    assert followed.status_code == 200, followed.text
    assert followed.json()["resolvedSegmentId"] == second["id"], "an old reference follows the merge"

    stable_route = json.loads(ROUTE_FIXTURE.read_text())

    def token_of(segment):
        return next(s["id"] for s in stable_route["segments"]
                    if s["kind"] == segment["kind"] and s["anchor"]["rect"] == segment["anchor"]["rect"])

    library = reference.split("/")[1]
    ids = {doc_id: stable_route["document_id"], first["id"]: token_of(first), second["id"]: token_of(second),
           library: "lib-0001", reference: f"fichero:segment/lib-0001/{stable_route['document_id']}/{token_of(first)}"}
    for index, note in enumerate(followed.json().get("segmentForwarding") or [], start=1):
        ids.setdefault(note.get("id"), f"forward-{index:04d}")
        ids.setdefault(note.get("audit_id"), f"audit-{index:04d}")
    stable = _stabilizer(ids)
    recorded = {"reference": ids[reference], "direct": stable(direct.json()), "after_merge": stable(followed.json())}
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        RESOLVE_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(RESOLVE_FIXTURE.read_text()) == recorded, "the app's reference fixture drifted"


EXPORT_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.export-choices.json"


def test_export_choices_are_recorded_as_edited_and_as_imported_for_the_making_section(db, client):
    """`source.format.export-choices`, `first-four`, `everywhere` (#5162, Inspector › Making's per-pass
    Export): the app lists what this build WRITES (GET /api/formats), exports one pass by its id in a
    chosen format -- the exact call, GET /api/documents/{id}/export/{format}?pass_id=… -- and saves the
    pass AS IMPORTED from its original (GET /api/segments/passes/{id}/original), whose bytes are the
    file's own, byte for byte. Recorded for the app. Breaks if a written format is not listed, the
    pass the person chose is not the one exported, or "as imported" is not the file as it arrived."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])

    formats = client.get("/api/formats").json()
    written = {f["name"] for f in formats["items"] if f["writes"]}
    assert {"pagexml", "alto", "tei", "hocr"} <= written
    exported = client.get(f"/api/documents/{doc_id}/export/hocr", params={"pass_id": real["id"]})
    assert exported.status_code == 200, exported.text
    assert exported.json()["choices"]["pass_id"] == real["id"], "the pass chosen is the pass exported"
    original = client.get(f"/api/segments/passes/{real['id']}/original").json()
    import base64
    assert base64.b64decode(original["content_base64"]) == SYRIAC.read_bytes(), "as imported, byte for byte"

    stable_route = json.loads(ROUTE_FIXTURE.read_text())
    ids = {doc_id: stable_route["document_id"],
           real["id"]: next(p["id"] for p in stable_route["passes"] if not p["provisional"])}
    by_rect = {repr(seg["anchor"]["rect"]): seg["id"] for seg in stable_route["segments"]}
    for segment in body["segments"]:
        ids.setdefault(segment["id"], by_rect.get(repr(segment["anchor"]["rect"]), segment["id"]))
    stable = _stabilizer(ids)
    answer = stable(exported.json())
    for raw, token in ids.items():  # the file names its segments inside its text, too
        answer["content"] = answer["content"].replace(raw, token)
    recorded = {"formats": formats, "export": answer, "original": stable(original),
                "original_sha256": __import__("hashlib").sha256(SYRIAC.read_bytes()).hexdigest()}
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        EXPORT_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(EXPORT_FIXTURE.read_text()) == recorded, "the app's export fixture drifted"


def _file_shapes(path: Path) -> dict[str, dict]:
    """Each TextLine's polygon and baseline as the PAGE file drew them, normalized to the page."""
    root = etree.parse(str(path)).getroot()
    page = next(el for el in root.iter() if isinstance(el.tag, str) and etree.QName(el).localname == "Page")
    width, height = float(page.get("imageWidth")), float(page.get("imageHeight"))

    def points(el):
        return [[float(x) / width, float(y) / height] for x, y in (p.split(",") for p in el.get("points").split())]

    shapes = {}
    for line in (el for el in root.iter() if isinstance(el.tag, str) and etree.QName(el).localname == "TextLine"):
        children = {etree.QName(c).localname: c for c in line if isinstance(c.tag, str)}
        shapes[line.get("id")] = {"polygon": points(children["Coords"]),
                                  "baseline": points(children["Baseline"]) if "Baseline" in children else None}
    return shapes


def test_an_imported_page_s_polygons_and_baselines_reach_the_app_as_the_file_drew_them_and_reshape_lands(db, client):
    """`source.segment.shape-kinds`, `curved-baseline`, `source.editor.reshape` (the overlay draws each
    shape as itself; Edit Segments reshapes it): every line of the imported Syriac PAGE page reaches the
    canvas's call (GET /api/segments/document/{id}) with the polygon and the baseline its file drew --
    checked point for point against the file with lxml -- and the recorded route the app plays back
    says the same. Then the app's EXACT reshapes land: `segment.update` with the polygon a vertex added
    and the rect its bounds, then with the baseline a point removed, each checked against the version
    read, each undone by its audit id. Breaks if a shape is lost or rounded on the way, or the edit the
    app sends is refused or does not write what was drawn."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    lines = [s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"]
    in_file = _file_shapes(SYRIAC)
    assert len(lines) == len(in_file) == 12

    def close(a, b):
        return a is not None and b is not None and len(a) == len(b) and all(
            abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9 for p, q in zip(a, b))

    for line in lines:
        match = [lid for lid, s in in_file.items() if close(s["polygon"], line["anchor"]["polygon"])]
        assert len(match) == 1, f"line {line['id']}'s polygon is not the file's"
        assert close(in_file[match[0]]["baseline"], line["baseline"]), "the baseline is the file's"
    recorded = {s["id"]: s for s in json.loads(ROUTE_FIXTURE.read_text())["segments"]}
    for line in lines:
        twin = next(s for s in recorded.values() if s["anchor"]["rect"] == line["anchor"]["rect"])
        assert twin["anchor"]["polygon"] == line["anchor"]["polygon"] and twin["baseline"] == line["baseline"]

    line = min(lines, key=lambda s: s["anchor"]["rect"])
    polygon = line["anchor"]["polygon"]
    a, b = polygon[0], polygon[1]
    reshaped = polygon[:1] + [[(a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 0.01]] + polygon[1:]
    xs, ys = [p[0] for p in reshaped], [p[1] for p in reshaped]
    rect = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
    anchor = {k: line["anchor"].get(k) for k in ("document_id", "page_id", "rendition_id", "space", "rotation", "granularity")}

    def invoke(name, params):
        answer = client.post("/api/actions/invoke", json={"name": name, "params": params})
        assert answer.status_code == 200, answer.text
        return answer.json()

    first = invoke("segment.update", {"segment_id": line["id"], "expected_version": line["version"],
                                      "anchor": dict(anchor, polygon=reshaped, rect=rect)})
    after = client.get(f"/api/segments/{line['id']}").json()["segment"]
    assert after["anchor"]["polygon"] == reshaped, "the vertex added is stored"
    assert after["baseline"] == line["baseline"], "a polygon reshape leaves the baseline alone"
    fewer = line["baseline"][:1] + line["baseline"][2:]
    second = invoke("segment.update", {"segment_id": line["id"], "expected_version": after["version"], "baseline": fewer})
    assert client.get(f"/api/segments/{line['id']}").json()["segment"]["baseline"] == fewer, "a point removed"
    stale = client.post("/api/actions/invoke", json={"name": "segment.update", "params": {
        "segment_id": line["id"], "expected_version": line["version"], "baseline": line["baseline"]}})
    assert stale.status_code == 409, "a reshape against a version somebody changed is refused"
    # ⌘Z twice, newest first: the baseline comes back, then the polygon.
    assert client.post(f"/api/actions/audit/{second['audit_id']}/undo").status_code == 200
    assert client.post(f"/api/actions/audit/{first['audit_id']}/undo").status_code == 200
    restored = client.get(f"/api/segments/{line['id']}").json()["segment"]
    assert restored["anchor"]["polygon"] == polygon and restored["baseline"] == line["baseline"]


PAGE_MESSAGES_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.page-messages.json"


def test_the_served_page_s_own_messages_are_recorded_for_the_app_s_bridge(db, client):
    """The JOINT of `source.textedit.*` (13b): the served Reader page's OWN script, run in node on the
    imported Syriac page, posts through its own `notify` into a stand-in `ficheroBridge` -- a run of
    typing on the first line (`readingEditMessage`), Keep Mine on it after somebody else's correction
    counts (`keepMineMessage`), Return in the middle of it (`lineSplitMessage`), and every one of its
    words deleted (`readingEditMessage` again) -- and exactly
    what it posted is recorded. The app's test feeds each posted body through the bridge's own parse
    and `ReaderTextEditRunner` (what `applyTextEdit` runs) and asserts the requests. Regenerated from
    the page every run: a change to the page's messages or to the app's reading of them breaks one of
    the two, never neither. Breaks if the page and the app stop agreeing on a message."""
    import shutil

    import pytest

    from tests.unit.api.test_reader_directions import _page_functions
    from tests.unit.api.test_reader_line_map import _node, _view

    if shutil.which("node") is None:
        pytest.skip("needs node to run the page's own script")
    doc_id = _import(db, SYRIAC)
    payload, html = _view(client, doc_id)
    page = payload["pages"][0]
    text, lines = page["content"], page["lines"]
    route = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in route["passes"] if not p["provisional"])
    first = min((s for s in route["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
                key=lambda s: s["anchor"]["rect"])
    mapped = next(line for line in lines if line["segment_id"] == first["id"])
    file_reading = mapped["representation_id"]
    theirs = client.post("/api/actions/invoke", json={"name": "representation.create", "params": {
        "document_id": doc_id, "segment_id": first["id"], "kind": "transcription",
        "content": text[mapped["char_start"]:mapped["char_end"]] + " (corrected)",
        "corrects_representation_id": file_reading}}).json()["result"]["id"]

    end = mapped["char_end"]
    typed = text[:end] + " ܘܐܝܣܚܩ" + text[end:]
    middle = (mapped["char_start"] + mapped["char_end"]) // 2
    emptied = text[:mapped["char_start"]] + text[mapped["char_end"]:]
    notify_start = html.index("function notify(kind, payload)")
    notify = html[notify_start:html.index("\n}\n", notify_start) + 3]
    posted = _node(_page_functions(html) + notify + f"""
const posts = [];
window.webkit = {{ messageHandlers: {{ ficheroBridge: {{ postMessage: (body) => posts.push(body) }} }} }};
const lines = {json.dumps(lines)}, pageId = {json.dumps(doc_id)}, segmentId = {json.dumps(first["id"])};
notify("readingEdit", readingEditMessage({json.dumps(text)}, {json.dumps(typed)}, lines, pageId, segmentId).message);
const mine = {json.dumps(text[mapped["char_start"]:mapped["char_end"]] + " ܘܐܝܣܚܩ")};
notify("readingEdit", keepMineMessage(pageId, segmentId,
    {{ mine, theirs: {{ representationId: {json.dumps(theirs)}, text: "theirs" }} }}));
notify("lineSplit", lineSplitMessage(lines, pageId, {middle}));
notify("readingEdit", readingEditMessage({json.dumps(text)}, {json.dumps(emptied)}, lines, pageId, segmentId).message);
console.log(JSON.stringify(posts));
""")
    assert [p["kind"] for p in posted] == ["readingEdit", "readingEdit", "lineSplit", "readingEdit"]
    assert posted[3]["text"] == "", "every word of the line deleted"
    assert posted[0]["basedOn"] == file_reading and posted[1]["basedOn"] == theirs

    stable_route = json.loads(ROUTE_FIXTURE.read_text())
    token = next(s["id"] for s in stable_route["segments"]
                 if s["kind"] == "line" and s["anchor"]["rect"] == first["anchor"]["rect"])
    recorded = _stabilizer({doc_id: stable_route["document_id"], first["id"]: token,
                            file_reading: "rep-0001", theirs: "rep-0002"})(posted)
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        PAGE_MESSAGES_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(PAGE_MESSAGES_FIXTURE.read_text()) == recorded, "the page's messages changed: re-record and re-run the app's joint test"


def test_the_shape_tool_s_polygon_and_baseline_become_segments_the_canvas_still_draws(db, client):
    """`source.editor.draw-shapes` (the one Shape tool's Polygon and Baseline in Edit Segments): on the
    imported Syriac page, the app's EXACT creates -- `segment.create` of a REGION anchored by its polygon
    and the rect it bounds, and of a LINE anchored by its baseline as an open path (no outline invented)
    with that baseline -- land on the shown pass; the canvas's call (GET /api/segments/document/{id})
    still numbers the pass's boxes 0..<count, so the page keeps drawing; and ⌘Z (the create's audit
    undone) takes each away. Breaks if a drawn shape is refused, stored as something else, or makes the
    pass undrawable."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    on_pass = next(s for s in body["segments"] if s["pass_id"] == real["id"])
    anchor = {k: on_pass["anchor"][k] for k in ("page_id", "rendition_id", "space") if on_pass["anchor"].get(k) is not None}
    polygon = [[0.1, 0.1], [0.3, 0.1], [0.3, 0.2], [0.1, 0.2], [0.05, 0.15]]
    baseline = [[0.2, 0.6], [0.5, 0.6], [0.8, 0.61]]

    def create(params):
        answer = client.post("/api/actions/invoke", json={"name": "segment.create", "params": params})
        assert answer.status_code == 200, answer.text
        return answer.json()

    region = create({"document_id": doc_id, "pass_id": real["id"], "kind": "region", "anchor": dict(
        anchor, document_id=doc_id, polygon=polygon, rect=[0.05, 0.1, 0.25, 0.1])})
    line = create({"document_id": doc_id, "pass_id": real["id"], "kind": "line", "baseline": baseline, "anchor": dict(
        anchor, document_id=doc_id, shapes=[{"kind": "path", "points": baseline}])})
    after = client.get(f"/api/segments/document/{doc_id}").json()
    mine = [s for s in after["segments"] if s["pass_id"] == real["id"]]
    assert sorted(s["box_index"] for s in mine) == list(range(len(mine))), "the pass still draws"
    made = {s["id"]: s for s in mine}
    drawn_region = made[region["result"]["segment_ids"][0]]
    drawn_line = made[line["result"]["segment_ids"][0]]
    assert drawn_region["kind"] == "region" and drawn_region["anchor"]["polygon"] == polygon
    assert drawn_line["kind"] == "line" and drawn_line["baseline"] == baseline
    assert drawn_line["anchor"]["shapes"][0]["kind"] == "path" and drawn_line["anchor"]["polygon"] is None
    for created in (line, region):
        assert client.post(f"/api/actions/audit/{created['audit_id']}/undo").status_code == 200
    left = {s["id"] for s in client.get(f"/api/segments/document/{doc_id}").json()["segments"]}
    assert drawn_region["id"] not in left and drawn_line["id"] not in left, "⌘Z takes each drawing away"


def test_reshaping_an_anchors_path_and_point_shapes_is_the_app_s_exact_update(db, client):
    """`source.editor.reshape` for the anchor's EXTRA shapes (an open path, a point): on the imported
    Syriac page, a line drawn by its baseline carries a path shape, and a point shape beside it; the
    app's exact reshape -- `segment.update` with the whole anchor sent back, the path's second point
    moved and the point nudged one pixel, every other shape and field carried -- lands as sent and
    undoes by its audit id. Breaks if a rewrite drops or reorders a shape, or the engine refuses it."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    path = [[0.2, 0.6], [0.5, 0.6], [0.8, 0.61]]
    point = [0.9, 0.62]
    shapes = [{"kind": "path", "points": path}, {"kind": "point", "points": [point]}]
    made = client.post("/api/actions/invoke", json={"name": "segment.create", "params": {
        "document_id": doc_id, "pass_id": real["id"], "kind": "line", "baseline": path,
        "anchor": {"document_id": doc_id, "shapes": shapes}}}).json()
    segment_id = made["result"]["segment_ids"][0]
    before = client.get(f"/api/segments/{segment_id}").json()["segment"]

    moved_path = [path[0], [0.5, 0.58], path[2]]
    nudged = [point[0] + 1 / 1969, point[1]]
    sent_shapes = [{"kind": "path", "points": moved_path, "t_start": None, "t_end": None},
                   {"kind": "point", "points": [nudged], "t_start": None, "t_end": None}]
    xs = [p[0] for p in moved_path + [nudged]]
    ys = [p[1] for p in moved_path + [nudged]]
    update = client.post("/api/actions/invoke", json={"name": "segment.update", "params": {
        "segment_id": segment_id, "expected_version": before["version"], "anchor": {
            "document_id": doc_id, "shapes": [{k: v for k, v in s.items() if v is not None} for s in sent_shapes],
            "rect": [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]}}})
    assert update.status_code == 200, update.text
    after = client.get(f"/api/segments/{segment_id}").json()["segment"]
    assert [s["kind"] for s in after["anchor"]["shapes"]] == ["path", "point"], "no shape dropped or reordered"
    assert after["anchor"]["shapes"][0]["points"] == moved_path
    assert after["anchor"]["shapes"][1]["points"] == [nudged]
    assert after["baseline"] == path, "a shape reshape leaves the baseline alone"
    assert client.post(f"/api/actions/audit/{update.json()['audit_id']}/undo").status_code == 200
    assert client.get(f"/api/segments/{segment_id}").json()["segment"]["anchor"]["shapes"][0]["points"] == path


FLOWS_ONTO_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.flows-onto-next-page.json"


def test_a_flow_that_could_continue_onto_the_next_page_is_recorded_and_continuing_it_is_the_app_s_exact_calls(db, client):
    """"Continue a Flow Here" (#5160 residue; `source.segment.flow`): a flow made on one imported Syriac
    page is offered on the NEXT imported page by the route the picker calls (GET
    /api/reading-orders/flows/onto/{page}); the answer is recorded for the app. Then the app's EXACT
    continuation -- `POST /api/reading-orders/{flow}/place {segment_id, at_end: true}` for each of the
    page's segments, in the page's order -- lands, and the flow then runs from the first page onto this
    one, which is no longer offered. Breaks if the flow is not offered, the places do not land at the
    end in order, or a continued flow is offered again."""
    from fichero_server.models import DocType, Document

    first_page = _import(db, SYRIAC)
    next_page = _import(db, SYRIAC)
    # Two pages of ONE source, in order: a flow is offered onto a later page of its own source.
    source = Document(name="Syriac manuscript", doc_type=DocType.file)
    db.save(source)
    for order, page_id in enumerate((first_page, next_page), start=1):
        page = db.get(Document, page_id)
        page.parent_id, page.doc_type, page.sort_order = source.id, DocType.page, order
        db.save(page)
    route = client.get(f"/api/segments/document/{first_page}").json()
    real = next(p for p in route["passes"] if not p["provisional"])
    flow = client.post("/api/actions/invoke", json={"name": "reading_order.create", "params": {
        "document_id": first_page, "pass_id": real["id"], "name": "Into the next page", "kind": "flow",
        "seed_from_pass": True}}).json()["result"]["order_id"]
    offered = client.get(f"/api/reading-orders/flows/onto/{next_page}").json()
    assert [f["order"]["id"] for f in offered["flows"]] == [flow]

    here = client.get(f"/api/segments/document/{next_page}").json()
    here_pass = next(p for p in here["passes"] if not p["provisional"])
    in_order = sorted((s for s in here["segments"] if s["pass_id"] == here_pass["id"]), key=lambda s: s["box_index"])
    before = len(client.get(f"/api/reading-orders/{flow}/entries").json()["entries"])
    for segment in in_order:
        placed = client.post(f"/api/reading-orders/{flow}/place", json={"segment_id": segment["id"], "at_end": True})
        assert placed.status_code == 200, placed.text
    entries = client.get(f"/api/reading-orders/{flow}/entries").json()["entries"]
    assert [e["segment_id"] for e in entries[before:]] == [s["id"] for s in in_order], "at the end, in the page's order"
    assert client.get(f"/api/reading-orders/flows/onto/{next_page}").json()["flows"] == [], "not offered again"

    stable_route = json.loads(ROUTE_FIXTURE.read_text())
    ids = {first_page: stable_route["document_id"], next_page: "doc-0002", flow: "order-0003", source.id: "source-0001",
           real["id"]: next(p["id"] for p in stable_route["passes"] if not p["provisional"])}
    by_rect = {repr(s["anchor"]["rect"]): s["id"] for s in stable_route["segments"]}
    for segment in route["segments"]:
        ids.setdefault(segment["id"], by_rect.get(repr(segment["anchor"]["rect"]), segment["id"]))
    recorded = _stabilizer(ids)(offered)
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        FLOWS_ONTO_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(FLOWS_ONTO_FIXTURE.read_text()) == recorded, "the app's flows-onto fixture drifted"


NO_READING_FIXTURE = FIXTURES / "syriac_onb-syr1-0001.no-reading.json"


def test_a_segment_with_no_reading_is_listed_as_such_and_typing_one_gives_it_text(db, client):
    """`source.textedit.deleting-words-keeps-ink`, its last clause: a segment left without a reading is
    SHOWN as such, never hidden. On the imported Syriac page a line is drawn by its baseline (the Shape
    tool's call) and has no reading: the canvas's call lists it with `text: null` -- which is what the
    app marks "No reading" -- beside the file's lines, whose text stands; an EMPTIED line is different,
    an empty reading (`text: ""`), not no reading. Then the app's exact "Type a Reading" --
    `representation.create` on that segment -- gives it text in the same call. Both answers are recorded
    for the app. Breaks if a reading-less segment drops out of the list, or reads as an empty one."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    lines = sorted((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
                   key=lambda s: s["anchor"]["rect"][1])
    baseline = [[0.2, 0.9], [0.5, 0.9], [0.8, 0.91]]
    drawn = client.post("/api/actions/invoke", json={"name": "segment.create", "params": {
        "document_id": doc_id, "pass_id": real["id"], "kind": "line", "baseline": baseline,
        "anchor": {"document_id": doc_id, "shapes": [{"kind": "path", "points": baseline}]}}}).json()
    drawn_id = drawn["result"]["segment_ids"][0]
    emptied = client.post("/api/actions/invoke", json={"name": "representation.create", "params": {
        "document_id": doc_id, "segment_id": lines[0]["id"], "kind": "transcription", "content": ""}})
    assert emptied.status_code == 200, emptied.text

    before = client.get(f"/api/segments/document/{doc_id}").json()
    by_id = {s["id"]: s for s in before["segments"]}
    assert by_id[drawn_id]["text"] is None, "no reading: listed, with no text"
    assert by_id[lines[0]["id"]]["text"] == "", "an emptied line is an empty reading, not no reading"
    assert all(by_id[s["id"]]["text"] for s in lines[1:]), "the file's lines keep their words"

    typed = client.post("/api/actions/invoke", json={"name": "representation.create", "params": {
        "document_id": doc_id, "segment_id": drawn_id, "kind": "transcription", "content": "ܫܠܡܐ"}})
    assert typed.status_code == 200, typed.text
    after = client.get(f"/api/segments/document/{doc_id}").json()
    assert {s["id"]: s for s in after["segments"]}[drawn_id]["text"] == "ܫܠܡܐ", "typing one gives it text"

    reduce = lambda answer: dict(answer, segments=[s for s in answer["segments"] if s["pass_id"] == real["id"]])  # noqa: E731
    stable_route = json.loads(ROUTE_FIXTURE.read_text())
    ids = {drawn_id: "seg-drawn-0001"}
    ids.update({s["id"]: t["id"] for s in body["segments"] for t in stable_route["segments"]
                if s["anchor"]["rect"] == t["anchor"]["rect"] and s["kind"] == t["kind"]})
    ids.update({doc_id: stable_route["document_id"], real["id"]:
                next(p["id"] for p in stable_route["passes"] if not p["provisional"])})
    stable = _stabilizer(ids)
    recorded = {"before": stable(reduce(before)), "after": stable(reduce(after))}
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        NO_READING_FIXTURE.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(NO_READING_FIXTURE.read_text()) == recorded, "the app's no-reading fixture drifted"


PDF_PAGE = Path(__file__).resolve().parents[2] / "fixtures" / "paleography" / "dialogo_lengua_page_18.pdf"


def test_a_pdf_page_given_a_page_file_s_lines_reaches_the_app_with_their_outlines_and_baselines(db, client):
    """Shapes on PDF pages (#5163 residue): a real PDF page (`dialogo_lengua_page_18.pdf`, the corpus's)
    given a PAGE file's lines through the one importer answers the canvas's call -- which the PDF
    renderer reads too (`PDFPageWithToolbar.loadOCRGeometry`) -- with every line's polygon and baseline
    exactly as the file drew them, so the PDF view can draw them as themselves
    (`PDFShapeAnnotations`, whose e2e opens this same PDF). Breaks if a PDF page loses the shapes an
    image page keeps."""
    from fichero_server.actions.registry import registry
    from fichero_server.models import DocType, Document, FileType, Status
    from tests.unit.api.test_page_text_follows_the_file import BOOT

    assert PDF_PAGE.is_file(), PDF_PAGE
    page = Document(name=PDF_PAGE.stem, doc_type=DocType.file, file_type=FileType.pdf, path=str(PDF_PAGE),
                    status=Status.completed)
    db.save(page)
    registry.invoke(db, "format.import", {"document_id": page.id, "path": str(SYRIAC)}, BOOT)
    body = client.get(f"/api/segments/document/{page.id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    lines = [s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"]
    in_file = _file_shapes(SYRIAC)
    assert len(lines) == len(in_file) == 12

    def close(a, b):
        return a is not None and b is not None and len(a) == len(b) and all(
            abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9 for p, q in zip(a, b))

    for line in lines:
        match = [lid for lid, s in in_file.items() if close(s["polygon"], line["anchor"]["polygon"])]
        assert len(match) == 1, "a PDF page keeps the file's outline"
        assert close(in_file[match[0]]["baseline"], line["baseline"]), "and its baseline"


def test_a_line_drawn_inside_a_region_is_that_region_s_line_in_its_order_and_one_undo_takes_both(db, client):
    """`source.editor.draw-shapes` (a drawn line lands in its region): on the imported Syriac page, the
    app's exact create for a baseline drawn at the foot of region 2 -- `segment.create` of a line with
    `parent_segment_id` = that region -- makes region 2's LAST line: its parent is the region, and the
    page's as-written order places it among region 2's lines where page order puts it (the foot, so last),
    not at the top level beside the regions, where a drawn line used to land. One undo of the create takes
    the line and its place. Breaks if a drawn line is orphaned at page level, lands among the regions in
    the order, or leaves its place behind when undone."""
    from fichero_server.api.routes.document.reading_orders import as_written_order, entries_in_sequence
    from fichero_server.models.reading_orders import ReadingOrderEntry

    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    regions = sorted((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "region"),
                     key=lambda s: (s["anchor"]["rect"][1], s["anchor"]["rect"][0]))
    region = regions[1]
    x, y, w, h = region["anchor"]["rect"]
    baseline = [[x + 0.1 * w, y + 0.97 * h], [x + 0.5 * w, y + 0.97 * h], [x + 0.9 * w, y + 0.975 * h]]
    order = as_written_order(db, real["id"])
    region_entry = next(e for e in db.query(ReadingOrderEntry, order_id=order.id) if e.segment_id == region["id"])
    lines_before = [e.segment_id for e in entries_in_sequence(db, order.id, parent_entry_id=region_entry.id)]

    made = client.post("/api/actions/invoke", json={"name": "segment.create", "params": {
        "document_id": doc_id, "pass_id": real["id"], "kind": "line", "baseline": baseline,
        "parent_segment_id": region["id"],
        "anchor": {"document_id": doc_id, "shapes": [{"kind": "path", "points": baseline}]}}})
    assert made.status_code == 200, made.text
    drawn_id = made.json()["result"]["segment_ids"][0]
    assert client.get(f"/api/segments/{drawn_id}").json()["segment"]["parent_segment_id"] == region["id"]
    lines_after = [e.segment_id for e in entries_in_sequence(db, order.id, parent_entry_id=region_entry.id)]
    assert lines_after == lines_before + [drawn_id], "region 2's last line, in the order"
    assert drawn_id not in [e.segment_id for e in entries_in_sequence(db, order.id)], "not beside the regions"

    placed = next(e for e in db.query(ReadingOrderEntry, order_id=order.id) if e.segment_id == drawn_id)
    export = lambda: client.get(f"/api/documents/{doc_id}/export/pagexml", params={"pass_id": real["id"]}).json()["content"]  # noqa: E731
    assert drawn_id in export(), "the export names the drawn line while it is there"

    undo = client.post(f"/api/actions/audit/{made.json()['audit_id']}/undo")
    assert undo.status_code == 200, undo.text
    left = {s["id"] for s in client.get(f"/api/segments/document/{doc_id}").json()["segments"]}
    assert drawn_id not in left
    # The undo takes the place out of the ORDER itself, not only out of one route's listing: every reader
    # of the order (export, flows, neighbours, the next/previous walk, the Reader's line map) reads this table.
    assert db.query(ReadingOrderEntry, segment_id=drawn_id) == [], "no row left for a segment that is gone"
    listed = client.get(f"/api/reading-orders/{order.id}/entries", params={"parent_entry_id": region_entry.id}).json()
    assert [e["segment_id"] for e in listed["entries"]] == lines_before, "one undo takes the line and its place"
    assert drawn_id not in export(), "nor does the PAGE export name it"

    redo = client.post(f"/api/actions/audit/{undo.json()['audit_id']}/undo")
    assert redo.status_code == 200, redo.text
    back = db.query(ReadingOrderEntry, segment_id=drawn_id)
    assert [(e.id, e.order_id, e.position, e.parent_entry_id) for e in back] == [
        (placed.id, placed.order_id, placed.position, placed.parent_entry_id)], "redo puts the entry back where it was"
    assert [e.segment_id for e in entries_in_sequence(db, order.id, parent_entry_id=region_entry.id)] == lines_before + [drawn_id]


def test_a_deleted_region_leaves_the_order_and_its_undo_puts_it_back_in_its_place(db, client):
    """The same class for `segment.delete` itself: deleting region 2 of the imported Syriac page takes its
    entry out of the as-written order -- the PAGE export's `<ReadingOrder>` no longer names it -- and one
    undo writes the SAME entry back (id, position, level), so its lines' entries, nested under it, are in
    the walk again. Breaks if a delete leaves a ghost row every reader of the order would meet, or its undo
    brings the region back at another place or none."""
    from fichero_server.api.routes.document.reading_orders import as_written_order, entries_in_sequence
    from fichero_server.models.reading_orders import ReadingOrderEntry

    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    order = as_written_order(db, real["id"])
    top = entries_in_sequence(db, order.id)
    entry = top[1]
    region = client.get(f"/api/segments/{entry.segment_id}").json()["segment"]
    lines = [e.segment_id for e in entries_in_sequence(db, order.id, parent_entry_id=entry.id)]
    assert lines, "region 2 has lines in the order"

    def reading_order_refs() -> list[str]:
        content = client.get(f"/api/documents/{doc_id}/export/pagexml", params={"pass_id": real["id"]}).json()["content"]
        tree = etree.fromstring(content.encode("utf-8"))
        return [el.get("regionRef") for el in tree.iter() if el.get("regionRef")]

    refs_before = reading_order_refs()
    deleted = client.post("/api/actions/invoke", json={"name": "segment.delete", "params": {
        "segment_ids": [region["id"]], "expected_versions": {region["id"]: region["version"]}}})
    assert deleted.status_code == 200, deleted.text
    assert db.query(ReadingOrderEntry, segment_id=region["id"]) == []
    assert region["id"] not in [e.segment_id for e in entries_in_sequence(db, order.id)]
    assert len(reading_order_refs()) == len(refs_before) - 1, "<ReadingOrder> names one region fewer"

    undo = client.post(f"/api/actions/audit/{deleted.json()['audit_id']}/undo")
    assert undo.status_code == 200, undo.text
    assert [(e.id, e.position, e.parent_entry_id) for e in entries_in_sequence(db, order.id)] == [
        (e.id, e.position, e.parent_entry_id) for e in top], "back at its own place, the same row"
    assert [e.segment_id for e in entries_in_sequence(db, order.id, parent_entry_id=entry.id)] == lines
    assert reading_order_refs() == refs_before


def _syriac_order(db, client):
    from fichero_server.api.routes.document.reading_orders import as_written_order

    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    return doc_id, real, as_written_order(db, real["id"])


def _page_export(client, doc_id, pass_id) -> str:
    return client.get(f"/api/documents/{doc_id}/export/pagexml", params={"pass_id": pass_id}).json()["content"]


def _reading_order_refs(content: str) -> list[str]:
    return [el.get("regionRef") for el in etree.fromstring(content.encode("utf-8")).iter() if el.get("regionRef")]


def test_a_merge_takes_the_absorbed_segment_out_of_the_order_and_its_undo_puts_the_same_row_back(db, client):
    """The class of 1052fda4a, for `segment.merge`: merging region 2 into region 1 of the imported Syriac
    page takes region 2's entry out of the as-written order -- the PAGE export's `<ReadingOrder>` names one
    region fewer -- and the undo (`segment.unmerge`) writes the SAME row back, so the order and the export
    are as they were; the redo takes it out again. Breaks if a merge leaves a ghost entry for a segment
    that is gone, or its undo brings the region back at another place or none."""
    from fichero_server.api.routes.document.reading_orders import entries_in_sequence
    from fichero_server.models.reading_orders import ReadingOrderEntry

    doc_id, real, order = _syriac_order(db, client)
    top = entries_in_sequence(db, order.id)
    keep = client.get(f"/api/segments/{top[0].segment_id}").json()["segment"]
    gone = client.get(f"/api/segments/{top[1].segment_id}").json()["segment"]
    refs_before = _reading_order_refs(_page_export(client, doc_id, real["id"]))

    merged = client.post("/api/actions/invoke", json={"name": "segment.merge", "params": {
        "segment_ids": [keep["id"], gone["id"]], "keep_id": keep["id"],
        "expected_versions": {keep["id"]: keep["version"], gone["id"]: gone["version"]}}})
    assert merged.status_code == 200, merged.text
    assert db.query(ReadingOrderEntry, segment_id=gone["id"]) == [], "no row for the absorbed region"
    assert len(_reading_order_refs(_page_export(client, doc_id, real["id"]))) == len(refs_before) - 1

    undo = client.post(f"/api/actions/audit/{merged.json()['audit_id']}/undo")
    assert undo.status_code == 200, undo.text
    assert [(e.id, e.position, e.parent_entry_id) for e in entries_in_sequence(db, order.id)] == [
        (e.id, e.position, e.parent_entry_id) for e in top], "the same row, at its own place"
    assert _reading_order_refs(_page_export(client, doc_id, real["id"])) == refs_before

    redo = client.post(f"/api/actions/audit/{undo.json()['audit_id']}/undo")
    assert redo.status_code == 200, redo.text
    assert db.query(ReadingOrderEntry, segment_id=gone["id"]) == [], "the redo takes it out again"


def test_a_split_line_s_new_part_follows_it_in_the_order_and_its_undo_takes_the_part_out(db, client):
    """`segment.split`'s parts had NO entry: a split line's second half was missing from every order,
    from the export's line order and from the Reader's walk. Now the new part follows the line it was
    cut from, at its level, in every order holding it -- in the PAGE export too -- and the undo
    (`segment.unsplit`) takes the part's entry out with the part; the redo mints a new part and places
    it the same way. Breaks if a split part is left out of the order, placed away from its line, or its
    entry outlives the undo."""
    from fichero_server.api.routes.document.reading_orders import entries_in_sequence
    from fichero_server.models.reading_orders import ReadingOrderEntry

    doc_id, real, order = _syriac_order(db, client)
    region_entry = entries_in_sequence(db, order.id)[1]
    lines = entries_in_sequence(db, order.id, parent_entry_id=region_entry.id)
    line = client.get(f"/api/segments/{lines[0].segment_id}").json()["segment"]
    x, y, w, h = line["anchor"]["rect"]
    half = {"document_id": doc_id}
    made = client.post("/api/actions/invoke", json={"name": "segment.split", "params": {
        "segment_id": line["id"], "expected_version": line["version"], "parts": [
            {"anchor": {**half, "rect": [x, y, w / 2, h]}},
            {"anchor": {**half, "rect": [x + w / 2, y, w / 2, h]}}]}})
    assert made.status_code == 200, made.text
    part = made.json()["result"]["new_segment_ids"][0]
    after = [e.segment_id for e in entries_in_sequence(db, order.id, parent_entry_id=region_entry.id)]
    assert after == [line["id"], part] + [e.segment_id for e in lines[1:]], "right after the line it was cut from"
    exported = _page_export(client, doc_id, real["id"])
    assert line["id"] in exported and part in exported
    assert exported.index(line["id"]) < exported.index(part), "and so in the export's line order"

    undo = client.post(f"/api/actions/audit/{made.json()['audit_id']}/undo")
    assert undo.status_code == 200, undo.text
    assert db.query(ReadingOrderEntry, segment_id=part) == [], "the part's entry leaves with the part"
    assert [e.segment_id for e in entries_in_sequence(db, order.id, parent_entry_id=region_entry.id)] == [
        e.segment_id for e in lines]
    assert part not in _page_export(client, doc_id, real["id"])

    redo = client.post(f"/api/actions/audit/{undo.json()['audit_id']}/undo")
    assert redo.status_code == 200, redo.text
    again = redo.json()["result"]["new_segment_ids"][0]
    assert [e.segment_id for e in entries_in_sequence(db, order.id, parent_entry_id=region_entry.id)][:2] == [line["id"], again]
