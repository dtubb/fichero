"""What `check_undo_coverage` may count as an undo registration.

It had no test, and it reported six endpoints as covered that nothing anywhere undoes: each
one matched a substring of its path inside a comment in a file that happens to mention
UndoManager. `POST /api/library` passed on the comment "document/library undo". The guard then
matched strictly -- and read ZERO, because it looked only for path strings, and the house rule
sends nearly every call through the generated client, whose methods are named for the
operationId and carry no path (#5144). Region edits that DO register ⌘Z read as gaps.

It now also counts the generated operation's name, in an undo-registering file, for an
operation whose answer carries the audit row a registration reverses. These tests fail if the
loose match comes back, if the operation-name witness goes blind again, or if it widens to
count a call merely because it sits in a file that registers undo for something else.
"""
from __future__ import annotations

import functools
import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_undo_coverage.py"
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC = importlib.util.spec_from_file_location("check_undo_coverage", _SCRIPT)
assert _SPEC and _SPEC.loader
check_undo_coverage = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_undo_coverage
_SPEC.loader.exec_module(check_undo_coverage)  # type: ignore[attr-defined]


@functools.lru_cache(maxsize=1)
def _rows() -> tuple:
    return tuple(check_undo_coverage.scan())


class TestTheSixFalsePositives:
    """Each of these was reported as having undo by a comment. None of them has any."""

    def test_the_library_endpoint_is_not_covered_by_a_comment_about_library_undo(self):
        """UndoRouting.swift:46 reads "document/library undo"; `/library` matched inside it."""
        rows = {row.endpoint: row for row in _rows()}
        assert rows["POST /api/library"].undo_registered is False
        assert rows["POST /api/library"].evidence == ()

    def test_the_pairing_endpoint_is_not_covered_by_the_word_pairing(self):
        rows = {row.endpoint: row for row in _rows()}
        assert rows["POST /api/pair"].undo_registered is False

    def test_the_rest_are_seeded_with_the_reason_they_stopped_passing(self):
        """A seeded gap has to say why, or the next reader cannot tell it from a deferral.
        `POST /api/actions/invoke` left this list with #5144: it IS registered (its audit id
        feeds the undo stack), found by the operation name, not by a comment."""
        for endpoint in (
            "POST /api/actions",
            "POST /api/authz/share",
            "POST /api/library",
            "POST /api/pair",
            "POST /api/workflows",
        ):
            reason = check_undo_coverage.KNOWN_GAPS[endpoint]
            assert "#5109" in reason, endpoint
            assert "comment" in reason, endpoint


class TestTheGeneratedClientIsSeen:
    """#5144, on the app's own tree."""

    def test_region_edits_that_register_undo_are_counted(self):
        rows = {row.endpoint: row for row in _rows()}
        row = rows["PUT /api/artifacts/{artifact_id}/regions"]
        assert row.undo_registered, "the region edit registers ⌘Z through ActionUndo"
        assert any("RegionCuration" in name for name in row.evidence)

    def test_a_call_beside_an_undo_registration_is_not_counted_for_it(self):
        """`createArtifact` sits in the same file as the region edits' registration and answers
        with no audit row; `share` sits beside `invokeAction`. Neither is undone."""
        rows = {row.endpoint: row for row in _rows()}
        assert rows["POST /api/artifacts/"].undo_registered is False
        assert rows["POST /api/authz/share"].undo_registered is False

    def test_every_covered_row_is_witnessed_by_an_undo_file(self):
        undo_files = {str(p.relative_to(check_undo_coverage.ROOT)) for p in check_undo_coverage.UNDO_SOURCES}
        for row in _rows():
            if row.undo_registered:
                assert row.evidence and set(row.evidence) <= undo_files, row


# --- the guard's own fixtures: a spec of two operations and Swift files written here ---------

_SPEC_FIXTURE = {
    "paths": {
        "/api/reading-orders/{order_id}/place": {
            "post": {
                "operationId": "place_in_reading_order_api_reading_orders__order_id__place_post",
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/ActionResponse"}}}}},
            }
        },
        "/api/things": {
            "post": {
                "operationId": "create_thing_api_things_post",
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"type": "object", "properties": {"id": {"type": "string"}}}}}}},
            }
        },
    },
    "components": {"schemas": {"ActionResponse": {
        "type": "object", "properties": {"ok": {}, "audit_id": {}, "result": {}}}}},
}
PLACE = "POST /api/reading-orders/{order_id}/place"
THING = "POST /api/things"


def _scan(tmp_path, **files: str) -> dict:
    paths = []
    for name, body in files.items():
        path = tmp_path / f"{name}.swift"
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    sources = check_undo_coverage.undo_sources(paths)
    return {row.endpoint: row for row in check_undo_coverage.scan(_SPEC_FIXTURE, sources)}


_REGISTERS = """
func place(_ id: String, undoManager: UndoManager?) async throws {
    let response = try await client.api.placeInReadingOrderApiReadingOrdersOrderIdPlacePost(.init(path: .init(orderId: id)))
    ActionUndo.register(auditId: try response.ok.body.json.auditId, actionName: "Place", undoManager: undoManager, performUndo: undo)
}
"""


def test_fixture_a_generated_call_that_registers_undo_is_covered(tmp_path):
    rows = _scan(tmp_path, ReadingOrderStore=_REGISTERS)
    assert rows[PLACE].undo_registered
    assert rows[PLACE].evidence == (str(tmp_path / "ReadingOrderStore.swift"),)


def test_fixture_the_same_call_without_undo_is_a_gap(tmp_path):
    no_undo = _REGISTERS.replace("undoManager: UndoManager?", "").replace(
        "ActionUndo.register(auditId: try response.ok.body.json.auditId, actionName: \"Place\", "
        "undoManager: undoManager, performUndo: undo)", "")
    assert "Undo" not in no_undo.replace("placeInReadingOrder", "")
    rows = _scan(tmp_path, ReadingOrderStore=no_undo)
    assert not rows[PLACE].undo_registered


def test_fixture_a_call_that_answers_no_audit_row_is_a_gap_even_in_an_undo_file(tmp_path):
    body = _REGISTERS + "\nfunc make() async throws { _ = try await client.api.createThingApiThingsPost(.init()) }\n"
    rows = _scan(tmp_path, Store=body)
    assert rows[PLACE].undo_registered
    assert not rows[THING].undo_registered


def test_fixture_the_operation_named_only_in_a_comment_is_a_gap(tmp_path):
    body = "// placeInReadingOrderApiReadingOrdersOrderIdPlacePost is undone elsewhere\nlet m: UndoManager? = nil\n"
    rows = _scan(tmp_path, Notes=body)
    assert not rows[PLACE].undo_registered


class TestTheScanStillSeesTheWholeSurface:
    def test_the_mutating_population_is_unchanged_by_the_stricter_match(self):
        """The fix tightened the witness, not the population: 393 mutating operations when it
        landed. A FLOOR, not an equality -- pinned exactly, this failed the day PATCH
        /api/segments was added (394), which is the surface growing, not the scan going blind.
        What must never happen is the count FALLING, because that means the scan stopped
        seeing routes it used to see and every "0 of N" figure quietly shrinks with it."""
        assert len(_rows()) >= 393

    def test_undo_registering_files_are_still_found(self):
        """If this drops to zero the guard has gone blind, which is worse than red."""
        assert len(check_undo_coverage.UNDO_SOURCES) >= 8


#: #4907: the five operations the 2026-09-19 review found with no undo surface. Each must stay
#: in the baseline with the reason it is not undoable, never the generic "pre-existing drift".
_REVIEWED_4907 = (
    "POST /api/hpc/clusters/{cluster_id}/test",
    "POST /api/kg/entity-curation/enrich/import",
    "POST /api/kg/entity-curation/enrich/preview",
    "POST /api/local-models/kraken/install",
    "PUT /api/settings/sparql-endpoints",
)


def test_each_reviewed_gap_records_why_it_is_not_undoable():
    known = check_undo_coverage.KNOWN_GAPS
    for endpoint in _REVIEWED_4907:
        reason = known.get(endpoint, "")
        assert reason, f"{endpoint} has no recorded reason"
        assert "pre-existing drift" not in reason, f"{endpoint}: {reason}"


def test_enrich_import_is_honestly_not_undoable_in_the_registry():
    """The baseline's reason for enrich/import is only true while the action says so."""
    from fichero_server.actions.registry import registry
    import fichero_server.api.routes.kg.entity_curation  # noqa: F401 -- registers the action

    assert registry.get("entity.enrich_import").undoable is False
    assert registry.get("claim.delete").undoable is True
