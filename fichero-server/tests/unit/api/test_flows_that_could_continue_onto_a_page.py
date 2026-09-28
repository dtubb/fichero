"""Which flows could continue onto a page, so the app can add the page's lines to one
(`source.segment.flow`; archive's request, 2026-09-28).

WHY: a letter's text runs from folio 3r to 3v; the reading that follows it is a `flow` order whose
entries cross pages. To continue it from 3v the app must be offered the flows that END BEFORE 3v --
not the page's own orders (the only ones it could list), not a flow that already reaches 3v (adding
to it again would loop the reading), not an as-written or imposed order (those never cross pages),
not a deleted one. And a flow on a page the caller may not read is not offered at all -- counted,
as every list does since #5180. If this regresses, the app cannot continue a flow across pages, or
offers one that would put a line in twice, or shows a denied page's flow.

Through the app's route and the audited `reading_order.*` actions, on a three-page source.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import ProjectInclusion
from tests.unit.api.test_segments_multiuser_access import (  # noqa: F401  (fixtures)
    _grant_role, _make_pass, _make_segment, _override, multiuser_client, users,
)

PERSON = ActionContext(actor="historian", is_bootstrap=True)


def _source(db, name, pages):
    source = Document(name=name, doc_type=DocType.file)
    db.save(source)
    out = []
    for i, label in enumerate(pages):
        page = Document(name=label, doc_type=DocType.page, parent_id=source.id, sort_order=i + 1)
        db.save(page)
        run = _make_pass(db, page.id)
        line = _make_segment(db, document_id=page.id, pass_id=run.id, rect=[0.1, 0.1, 0.5, 0.04])
        out.append((page, run, line))
    return source, out


def _flow(db, page, run, lines, name, kind="flow"):
    order = registry.invoke(db, "reading_order.create", {"document_id": page.id, "pass_id": run.id,
                                                          "name": name, "kind": kind}, PERSON).result["order_id"]
    for line in lines:
        registry.invoke(db, "reading_order.place", {"order_id": order, "segment_id": line.id, "at_end": True}, PERSON)
    return order


def _offered(client, page_id, headers=None):
    response = client.get(f"/api/reading-orders/flows/onto/{page_id}", headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_flow_ending_on_an_earlier_page_is_offered_nearest_first(db, client):
    _source_, [(p1, r1, l1), (p2, r2, l2), (p3, _r3, _l3)] = _source(db, "Letter", ["3r", "3v", "4r"])
    ends_on_3r = _flow(db, p1, r1, [l1], "the salutation")
    runs_to_3v = _flow(db, p1, r1, [l1, l2], "the body")                   # crosses 3r -> 3v
    _flow(db, p1, r1, [l1], "a commentary", kind="commentary")                # never crosses pages
    gone = _flow(db, p1, r1, [l1], "withdrawn")
    registry.invoke(db, "reading_order.delete", {"order_id": gone}, PERSON)

    onto_4r = _offered(client, p3.id)["flows"]
    assert [(f["order"]["id"], f["last_page_id"], f["relation"]) for f in onto_4r] == [
        (runs_to_3v, p2.id, "earlier page"), (ends_on_3r, p1.id, "earlier page")]     # 3v is nearer than 3r
    assert onto_4r[0]["last_segment_id"] == l2.id

    onto_3v = _offered(client, p2.id)["flows"]
    assert [f["order"]["id"] for f in onto_3v] == [ends_on_3r]        # "the body" already reaches 3v
    assert _offered(client, p1.id)["flows"] == []                     # nothing comes before the first page


def test_a_flow_on_a_source_the_page_shares_a_project_with_is_offered_and_marked(db, client):
    letter, [(p1, _r1, _l1), (p2, _r2, _l2)] = _source(db, "Letter", ["3r", "3v"])
    register, [(q1, s1, m1)] = _source(db, "Register", ["f. 12"])
    copied = _flow(db, q1, s1, [m1], "the copy in the register")
    for target in (letter.id, register.id):
        db.save(ProjectInclusion(project_id="the-case", target_id=target, target_type="document"))
    onto = _offered(client, p1.id)["flows"]
    assert [(f["order"]["id"], f["relation"]) for f in onto] == [(copied, "same project")]


def test_a_flow_on_a_page_the_caller_may_not_read_is_withheld_and_counted(multiuser_client, app_db, users, db):
    client, login, library_path = multiuser_client
    _grant_role(app_db, users.editor, library_path, "viewer")
    _source_, [(p1, r1, l1), (p2, r2, l2), (p3, _r3, _l3)] = _source(db, "Letter", ["3r", "3v", "4r"])
    _flow(db, p1, r1, [l1], "on a denied page")
    open_flow = _flow(db, p2, r2, [l2], "on an open page")
    _override(app_db, users.editor, library_path, p1.id, "deny")
    body = _offered(client, p3.id, login("editor"))
    assert [f["order"]["id"] for f in body["flows"]] == [open_flow] and body["withheld"] == 1
