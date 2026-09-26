"""Setting the cascade's facts above a segment, and the one resolve read (#4938).

`source_setting.set` / `.clear` and `GET /api/source-settings/resolve`.

Ruled 2026-09-26 (option A): this action owns the PROJECT and NODE levels and
refuses `level="segment"`, because `segment.update` already owns a segment's
version snapshot, stale check, inverse and audit row — and routing a segment's
language elsewhere would make it the only segment action that cannot change some
of the segment's own columns, which is a trap rather than untidiness.

The asymmetry is asserted here, not just documented: a test reads the refusal's
message and requires it to name the alternative.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.llm.language_policy import (
    LEVEL_DOCUMENT,
    LEVEL_PROJECT,
    SOURCE_DERIVED_FROM_SCRIPT,
    SOURCE_DETECTED,
    SOURCE_USER,
)
from fichero_server.models import Document, DocType, FileType, Status
from fichero_server.models.source_declarations import (
    ENCODING_PART,
    declare_script,
    name_registered_script,
    project_facts,
)
import fichero_server.api.routes.document.source_settings  # noqa: F401

pytestmark = pytest.mark.source_model


def _person() -> ActionContext:
    return ActionContext(actor="historian", is_bootstrap=True)


def _runner() -> ActionContext:
    return ActionContext(actor="runner", run_id="run-1", is_bootstrap=True)


def _set(db, *, ctx: ActionContext | None = None, **params):
    return registry.invoke(db, "source_setting.set", params, ctx or _person())


def _clear(db, *, ctx: ActionContext | None = None, **params):
    return registry.invoke(db, "source_setting.clear", params, ctx or _person())


def _document(db, name: str = "ledger.jpg") -> Document:
    doc = Document(
        name=name, doc_type=DocType.file, file_type=FileType.image,
        path=f"/path/{name}", status=Status.completed,
    )
    db.save(doc)
    return doc


class TestTheProjectLevel:
    def test_a_project_states_a_script(self, db):
        _set(db, level="project", key="script", value="Arab")

        facts = project_facts(db)
        assert facts.script == "Arab"
        assert facts.script_meta["level"] == LEVEL_PROJECT
        assert facts.script_meta["source"] == SOURCE_USER

    def test_a_runs_setting_is_not_recorded_as_a_persons(self, db):
        _set(db, level="project", key="language", value="Spanish", ctx=_runner())

        assert project_facts(db).language_meta["source"] == SOURCE_DETECTED

    def test_an_agent_acting_through_mcp_is_not_recorded_as_a_person(self, db):
        """The #4868/#4869 defect, one level up. An agent sets `via_mcp` and NO
        `run_id`, so a local "an actor and no run means a person" test would have
        recorded its determination as a curator's judgement — permanently, and
        indistinguishably. The one `provenance_kind_from_ctx` rule is what
        prevents it, and this is the test that would have caught my own version."""
        _set(
            db, level="project", key="language", value="Spanish",
            ctx=ActionContext(actor="claude", via_mcp=True, is_bootstrap=True),
        )

        assert project_facts(db).language_meta["source"] != SOURCE_USER
        assert project_facts(db).language_meta["source"] == SOURCE_DETECTED

    def test_clearing_returns_the_project_to_never_determined(self, db):
        _set(db, level="project", key="direction", value="rtl")
        _clear(db, level="project", key="direction")

        assert project_facts(db).direction is None

    def test_an_empty_value_is_refused_rather_than_silently_clearing(self, db):
        """Two different acts need two different calls, or a caller that meant to
        correct a typo silently withdraws a statement."""
        with pytest.raises(HTTPException) as raised:
            _set(db, level="project", key="script", value="")
        assert raised.value.status_code == 422
        assert "clear" in str(raised.value.detail)


class TestTheNodeLevel:
    def test_a_document_carries_its_own_three_facts(self, db):
        doc = _document(db)

        _set(db, level="node", target_id=doc.id, key="script", value="Latn")
        _set(db, level="node", target_id=doc.id, key="direction", value="ltr")

        stored = db.get(Document, doc.id)
        assert stored.script == "Latn"
        assert stored.direction == "ltr"
        assert stored.script_meta["level"] == LEVEL_DOCUMENT

    def test_the_node_level_needs_to_know_which_node(self, db):
        with pytest.raises(HTTPException) as raised:
            _set(db, level="node", key="script", value="Latn")
        assert raised.value.status_code == 422
        assert "target_id" in str(raised.value.detail)

    def test_a_missing_node_is_a_404_not_a_silent_no_op(self, db):
        with pytest.raises(HTTPException) as raised:
            _set(db, level="node", target_id="no-such-node", key="script", value="Latn")
        assert raised.value.status_code == 404

    def test_clearing_a_node_drops_the_provenance_with_the_value(self, db):
        doc = _document(db)
        _set(db, level="node", target_id=doc.id, key="script", value="Latn")

        _clear(db, level="node", target_id=doc.id, key="script")

        stored = db.get(Document, doc.id)
        assert stored.script is None
        assert stored.script_meta is None


class TestTheSegmentLevelIsElsewhereAndSaysSo:
    def test_setting_a_segments_fact_here_is_refused(self, db):
        with pytest.raises(HTTPException) as raised:
            _set(db, level="segment", target_id="seg-1", key="script", value="Latn")
        assert raised.value.status_code == 422

    def test_the_refusal_names_the_action_that_does_it(self, db):
        """Condition on the ruling: a refusal that says only "not supported here"
        sends the reader hunting through the registry for something one call away."""
        with pytest.raises(HTTPException) as raised:
            _set(db, level="segment", target_id="seg-1", key="script", value="Latn")

        message = str(raised.value.detail)
        assert "segment.update" in message
        assert "segment.facts_clear" in message

    def test_clearing_a_segments_fact_here_is_refused_the_same_way(self, db):
        with pytest.raises(HTTPException) as raised:
            _clear(db, level="segment", target_id="seg-1", key="script")
        assert "segment.update" in str(raised.value.detail)

    def test_an_unknown_level_is_refused_and_the_levels_are_named(self, db):
        with pytest.raises(HTTPException) as raised:
            _set(db, level="folder", key="script", value="Latn")
        assert "project" in str(raised.value.detail)
        assert "node" in str(raised.value.detail)


class TestTheSameInvariantsAtEveryLevel:
    """The sibling-defect shape is a validated segment path beside an unvalidated
    project one. These assert the project and node levels refuse what the segment
    level refuses."""

    def test_an_undeclared_private_use_script_is_refused_at_the_project_level(self, db):
        with pytest.raises(HTTPException) as raised:
            _set(db, level="project", key="script", value="Qabs")
        assert raised.value.status_code == 422
        assert "declare" in str(raised.value.detail)

    def test_the_same_code_is_accepted_once_the_project_declares_it(self, db):
        declare_script(db, "Qabs", "The clerk's hand")

        _set(db, level="project", key="script", value="Qabs")

        assert project_facts(db).script == "Qabs"

    def test_an_undeclared_private_use_script_is_refused_at_the_node_level(self, db):
        doc = _document(db)
        with pytest.raises(HTTPException) as raised:
            _set(db, level="node", target_id=doc.id, key="script", value="Qabr")
        assert raised.value.status_code == 422

    def test_a_direction_outside_the_six_is_refused_at_both_levels(self, db):
        doc = _document(db)
        for params in (
            {"level": "project", "key": "direction", "value": "sideways"},
            {"level": "node", "target_id": doc.id, "key": "direction", "value": "sideways"},
        ):
            with pytest.raises(HTTPException) as raised:
                _set(db, **params)
            assert "follows-baseline" in str(raised.value.detail)

    def test_encoding_cannot_be_set_at_any_level(self, db):
        """It is a property of the SCRIPT, on the script row. Accepting it here
        would be the second home for one fact."""
        with pytest.raises(HTTPException) as raised:
            _set(db, level="project", key="encoding", value="full")
        assert raised.value.status_code == 422


class TestUndo:
    def test_undoing_a_set_restores_the_previous_value(self, db):
        """Asserts the inverse RECIPE and then RUNS it, so this proves the undo
        actually restores the value rather than that a function returns a tuple."""
        from fichero_server.api.routes.document.source_settings import (
            _invert_source_setting_set,
        )

        _set(db, level="project", key="script", value="Latn")
        _set(db, level="project", key="script", value="Arab")
        assert project_facts(db).script == "Arab"

        name, params = _invert_source_setting_set(
            {"level": "project", "key": "script", "target_id": None, "value": "Latn"},
            {"level": "project", "key": "script", "target_id": None, "value": "Arab"},
            _person(),
        )
        assert name == "source_setting.set"
        registry.invoke(db, name, params, _person())

        assert project_facts(db).script == "Latn"

    def test_undoing_the_FIRST_set_clears_rather_than_restoring_nothing(self, db):
        from fichero_server.api.routes.document.source_settings import (
            _invert_source_setting_set,
        )

        name, params = _invert_source_setting_set(
            {"level": "project", "key": "script", "target_id": None, "value": None},
            {"level": "project", "key": "script", "target_id": None, "value": "Arab"},
            _person(),
        )

        # There was nothing before, so undo must REMOVE the statement, not write
        # an empty one -- an empty statement is a claim that somebody looked.
        assert name == "source_setting.clear"
        assert "value" not in params


class TestTheResolveRead:
    def test_it_says_which_rung_answered_for_each_fact(self, db, client):
        doc = _document(db)
        _set(db, level="project", key="script", value="Arab")
        name_registered_script(db, "Arab", "Arabic", encoding=ENCODING_PART)

        response = client.get(f"/api/source-settings/resolve?document_id={doc.id}")
        assert response.status_code == 200, response.text
        answers = {item["key"]: item for item in response.json()["settings"]}

        assert answers["script"]["value"] == "Arab"
        assert answers["script"]["level"] == LEVEL_PROJECT
        # Direction was stated nowhere, so it is DERIVED from that script -- and
        # says so on the source axis, with no rung claimed.
        assert answers["direction"]["value"] == "rtl"
        assert answers["direction"]["source"] == SOURCE_DERIVED_FROM_SCRIPT
        assert answers["direction"]["level"] is None
        # And the encoding comes from the script row, not from any level.
        assert answers["encoding"]["value"] == ENCODING_PART

    def test_a_node_value_overrides_the_project_in_the_answer(self, db, client):
        doc = _document(db)
        _set(db, level="project", key="script", value="Arab")
        _set(db, level="node", target_id=doc.id, key="script", value="Latn")

        response = client.get(f"/api/source-settings/resolve?document_id={doc.id}")
        answers = {item["key"]: item for item in response.json()["settings"]}

        assert answers["script"]["value"] == "Latn"
        assert answers["script"]["level"] == LEVEL_DOCUMENT

    def test_an_unstated_fact_reads_as_unknown_with_a_reason(self, db, client):
        doc = _document(db)

        response = client.get(f"/api/source-settings/resolve?document_id={doc.id}")
        answers = {item["key"]: item for item in response.json()["settings"]}

        assert answers["script"]["value"] is None
        assert answers["script"]["status"] == "unknown"
        assert answers["script"]["basis"]
        assert answers["encoding"]["value"] is None

    def test_a_missing_document_is_a_404(self, db, client):
        response = client.get("/api/source-settings/resolve?document_id=no-such-doc")
        assert response.status_code == 404


class TestThePutRoute:
    def test_it_states_and_then_stops_stating_one_fact(self, db, client):
        response = client.put(
            "/api/source-settings", json={"level": "project", "key": "script", "value": "Latn"}
        )
        assert response.status_code == 200, response.text
        assert project_facts(db).script == "Latn"

        # `value: null` is the same act as `source_setting.clear`, routed to it:
        # one control in the app, one endpoint.
        response = client.put(
            "/api/source-settings", json={"level": "project", "key": "script", "value": None}
        )
        assert response.status_code == 200, response.text
        assert project_facts(db).script is None
