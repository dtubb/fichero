"""`source.textedit.*` (#5001), the engine-side primitives — read from what the code DOES rather
than the spec's own `[GAP]` tags, which the maintainer asked not to be trusted on their face.

Findings, per behaviour, reported alongside these tests:

* `source.textedit.typing-is-a-new-reading` -- WHOLE on the engine side. `representation.create`
  sets the maker from `ActionContext` (`provenance_kind_from_ctx`, the same function #4868/#4869
  fixed), never from client input, and no update action exists for a reading at all -- "the
  earlier reading stays" is true by there being no other way to change one. Pinned below with the
  request shape the app would actually send (a real actor, no run_id, no via_mcp), not a clean id
  constructed for the test.
* `source.textedit.reader-shows-segments` -- PARTIAL. `document_text` already reads the working
  pass and follows the named order (proven below); `DerivedTextSpan` has no region grouping and no
  per-block direction, so "one block for each region and direction" is not built. Pinned as what
  IS true today; the packaging gap is not invented here.
* `source.textedit.return-splits-the-line` -- PARTIAL. `segment.split` takes an independent
  `reading_span` (text offset) and `anchor` (geometry) per part -- proven below -- but nothing
  computes one from the other. A caret index into a reading, mapped to a geometric cut point
  along a baseline (word-aligned when word children exist, proportional and marked estimated
  otherwise, direction-aware for RTL/boustrophedon), does not exist anywhere in the tree. Not
  invented here: the "estimated" proportional algorithm is a design decision, not a gap to fill
  freehand.
"""
from __future__ import annotations

import pytest

import fichero_server.api.routes.document.content_representations  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_conversion import live_rows_in_order
from fichero_server.models import Artifact
from fichero_server.models.anchors import SourceAnchor

from .seeded_converted_page import seed_page

pytestmark = pytest.mark.source_model


def _converted(db, client):
    _, page, art = seed_page(db)
    r = client.put(f"/api/artifacts/{art.id}/regions", json={"op": "move", "indices": [0], "bbox": [0.1, 0.1, 0.6, 0.05]})
    assert r.status_code == 200
    row = live_rows_in_order(db, db.get(Artifact, art.id).geometry_superseded_by_pass_id)[0]
    return page, art, row


class TestTypingIsANewReadingSetsTheMakerFromContext:
    """The maker is set BY THE ENGINE from the request's own actor -- never trusted from what a
    caller claims -- because #4868/#4869 was exactly a client-shaped default winning silently."""

    def test_a_real_actors_correction_is_recorded_as_human(self, db, client):
        page, art, row = _converted(db, client)
        # The value the app would actually send: a real historian's name, no run_id, no via_mcp --
        # never a clean synthetic id built to make the assertion easy.
        ctx = ActionContext(actor="dtubb", library_path=None, is_bootstrap=True)
        result = registry.invoke(db, "representation.create", {
            "document_id": page.id, "segment_id": row.id, "kind": "transcription",
            "content": "In the year of Our Lord and Saviour"}, ctx).result
        from fichero_server.models import ContentRepresentation
        saved = db.get(ContentRepresentation, result["id"])
        assert saved.provenance_kind.value == "human"
        assert saved.created_by == "dtubb"

    def test_a_workflow_runs_correction_is_recorded_as_workflow_not_human(self, db, client):
        page, art, row = _converted(db, client)
        ctx = ActionContext(actor="dtubb", library_path=None, is_bootstrap=True, run_id="run-123")
        result = registry.invoke(db, "representation.create", {
            "document_id": page.id, "segment_id": row.id, "kind": "transcription",
            "content": "a machine-run reading"}, ctx).result
        from fichero_server.models import ContentRepresentation
        saved = db.get(ContentRepresentation, result["id"])
        # A run behind the call outranks the actor name: a workflow acting AS dtubb is still a
        # machine's output, and recording it as human would be the #4868/#4869 shape again.
        assert saved.provenance_kind.value == "workflow"

    def test_a_client_supplied_maker_is_refused_not_honoured(self):
        """`RepresentationCreateParams` has no `created_by`/`provenance_kind` field at all
        (`extra="forbid"`), so a caller cannot claim to be the maker -- the engine is the only
        thing that can ever say so."""
        from fichero_server.api.routes.document.content_representations import RepresentationCreateParams
        with pytest.raises(Exception):
            RepresentationCreateParams(document_id="d", kind="transcription", content="x", created_by="someone")

    def test_the_earlier_reading_is_unchanged_by_a_correction(self, db, client):
        """'the earlier reading stays' -- because there is no update action for a reading at all,
        proven by writing a second reading and reading the first back unchanged."""
        page, art, row = _converted(db, client)
        ctx = ActionContext(actor="dtubb", library_path=None, is_bootstrap=True)
        first = registry.invoke(db, "representation.create", {
            "document_id": page.id, "segment_id": row.id, "kind": "transcription",
            "content": "In the year of our Lord"}, ctx).result
        registry.invoke(db, "representation.create", {
            "document_id": page.id, "segment_id": row.id, "kind": "transcription",
            "content": "In the year of Our Lord and Saviour"}, ctx)
        from fichero_server.models import ContentRepresentation
        still_there = db.get(ContentRepresentation, first["id"])
        assert still_there is not None and still_there.content == "In the year of our Lord"


class TestReaderShowsSegmentsUsesTheWorkingPassAndNamedOrder:
    """What IS built: `document_text` reads the working pass in the named (box) order and links
    every span back to its segment. NOT built, and not asserted here: grouping into one block per
    region, or per-block direction -- `DerivedTextSpan` carries neither."""

    def test_the_derived_text_follows_the_working_pass_and_names_its_segments(self, db, client):
        page, art, row = _converted(db, client)
        body = client.get(f"/api/segments/document/{page.id}/text").json()
        assert body["pass_id"] == db.get(Artifact, art.id).geometry_superseded_by_pass_id
        assert [s["segment_id"] for s in body["spans"]][0] == row.id

    def test_spans_carry_no_region_grouping_or_direction_today(self, db, client):
        """Pinned so a future change to `DerivedTextSpan` is a deliberate decision, not a silent
        drift -- this is the packaging gap the spec's `reader-shows-segments` still needs."""
        page, art, row = _converted(db, client)
        body = client.get(f"/api/segments/document/{page.id}/text").json()
        span = body["spans"][0]
        assert set(span.keys()) == {"segment_id", "representation_id", "start", "end"}


class TestReturnSplitsTheLineSegmentSplitPrimitive:
    """What IS built: `segment.split` takes an independent geometric `anchor` and an independent
    text `reading_span` per part -- the primitive the spec's Return handler would call. NOT built,
    and not invented here: computing one from a caret offset (word-aligned or proportional,
    direction-aware)."""

    def test_a_split_takes_an_independent_anchor_and_reading_span_per_part(self, db, client):
        page, art, row = _converted(db, client)
        ctx = ActionContext(actor="dtubb", library_path=None, is_bootstrap=True)
        rid = registry.invoke(db, "representation.create", {
            "document_id": page.id, "segment_id": row.id, "kind": "transcription",
            "content": "In the year of our Lord"}, ctx).result["id"]
        registry.invoke(db, "reading.choose", {"segment_id": row.id, "kind": "transcription", "representation_id": rid}, ctx)
        left = SourceAnchor(document_id=page.id, rect=[0.1, 0.1, 0.3, 0.05])
        right = SourceAnchor(document_id=page.id, rect=[0.4, 0.1, 0.3, 0.05])
        result = registry.invoke(db, "segment.split", {
            "segment_id": row.id,
            "parts": [
                {"anchor": left.model_dump(mode="json"), "reading_span": [0, 12]},
                {"anchor": right.model_dump(mode="json"), "reading_span": [12, 24]},
            ],
            "expected_version": row.version,
        }, ctx).result
        assert len(result["new_segment_ids"]) == 1
        assert result["kept_id"] == row.id

    def test_no_caret_to_geometry_mapping_exists_in_the_tree(self):
        """Confirms absence rather than assuming it: grepped for the shapes the spec's fallback
        names (word-aligned cut, proportional-along-baseline estimate) and found none. This is
        the one piece of `return-splits-the-line` that is genuinely unbuilt, not merely unwired."""
        import re
        from pathlib import Path

        server_src = Path(__file__).resolve().parents[4] / "src" / "fichero_server"
        hits = []
        for path in server_src.rglob("*.py"):
            text = path.read_text(errors="ignore")
            if re.search(r"proportion.*baseline|baseline.*proportion|caret.*offset|offset.*caret", text, re.I):
                hits.append(str(path))
        assert hits == [], f"a caret-to-geometry mapping may already exist: {hits}"
