"""Source-model slice 2 (#4920) — the change stream learns segment ids.

Engine half only: `ChangeEvent`/`emit_change` gain `segment_ids`/`pass_ids`,
`CHANGE_ID_LISTS` becomes the one place a new kind is declared, and every id
list is de-duplicated with order kept. Nothing emits a segment event yet —
no segment action exists until slice 4 — so there is no emitter to test here,
only the seam.

Spec: docs/contributor_manual/specs/source/build-notes-identity-and-storage.md,
"Slice 2 — the change stream names segments and passes". Each test names the
behaviour id it pins.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pydantic import BaseModel

from fichero_server.actions.registry import (
    ActionContext,
    ActionRegistration,
    ChangeSpec,
    registry,
)
from fichero_server.api import change_stream
from fichero_server.api.change_stream import CHANGE_ID_LISTS, ChangeEvent, emit_change
from fichero_server.api.routes.system.activity import _change_event_to_activity_response

pytestmark = pytest.mark.source_model

#: Committed fixture the Swift-side contract test reads (app lane owns that
#: half). Not named in the build note, so placed under tests/contracts/ per
#: the manager's instruction, and reported.
FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "contracts" / "change_event_all_id_lists.json"
)

#: Set to regenerate the committed fixture; unset (the normal case) compares
#: against it instead of writing, so a stale committed copy FAILS rather than
#: being silently overwritten (review fix 1, slice-2-engine-review.md).
_REGENERATE_ENV = "FICHERO_REGENERATE_CONTRACT_FIXTURES"
_REGENERATE_CMD = (
    f"{_REGENERATE_ENV}=1 pytest "
    "fichero-server/tests/unit/api/test_change_stream_segment_ids.py"
    "::TestCrossLanguageContractFixture -q"
)


def _build_fixture_event() -> ChangeEvent:
    """Deterministic contract fixture: a FIXED timestamp and fixed ids
    generated from `CHANGE_ID_LISTS`, never a real one -- a real timestamp
    would dirty the tree on every run and a stale committed fixture would
    never fail anywhere."""
    payload = {name: [f"{name}-fixture"] for name in CHANGE_ID_LISTS}
    return ChangeEvent(
        type="test.contract_fixture", ts="2026-01-01T00:00:00+00:00", **payload
    )


class TestChangeIdListsTuple:
    def test_declares_every_old_kind_plus_segment_and_pass(self):
        """source.events.segment-ids. `CHANGE_ID_LISTS` is the one place a
        new kind is added -- pin its membership so nobody edits `emit_change`
        by hand again without also touching the tuple."""
        assert CHANGE_ID_LISTS == (
            "entity_ids", "claim_ids", "document_ids", "artifact_ids",
            "citation_ids", "reference_ids", "interpretation_ids",
            "segment_ids", "pass_ids",
        )

    def test_tuple_matches_changeevent_changespec_and_emit_change_exactly(self):
        """Review follow-up (3): a name in the tuple missing from
        `ChangeEvent`, `ChangeSpec` or `emit_change`'s keywords raises inside
        `emit_change`'s `except Exception` and silently stops EVERY change
        event. Pin the alignment directly rather than trust the round trip
        to notice."""
        import dataclasses
        import inspect

        event_id_fields = {
            name for name in ChangeEvent.model_fields if name.endswith("_ids")
        }
        # `target_ids` also ends `_ids` but is NOT a CHANGE_ID_LISTS kind --
        # it populates ActionResult.changed_domains / the audit row, never
        # emit_change. Excluded deliberately, not missed.
        spec_id_fields = {
            f.name
            for f in dataclasses.fields(ChangeSpec)
            if f.name.endswith("_ids") and f.name != "target_ids"
        }
        emit_change_id_kwargs = {
            name
            for name in inspect.signature(emit_change).parameters
            if name.endswith("_ids")
        }

        assert set(CHANGE_ID_LISTS) == event_id_fields
        assert set(CHANGE_ID_LISTS) == spec_id_fields
        assert set(CHANGE_ID_LISTS) == emit_change_id_kwargs


class TestRoundTripEveryDeclaredKindBothPaths:
    def test_every_kind_reaches_the_direct_stream_and_the_activity_fold(self, monkeypatch):
        """source.events.segment-ids. One round trip per declared kind,
        through BOTH paths: the direct-stream subscriber (`_change_hub.emit`)
        and the activity fold (`_change_event_to_activity_response`). Iterates
        `CHANGE_ID_LISTS`, so a kind added later is covered with no test edit —
        closing the four-site silent-omission class from the recon."""
        for name in CHANGE_ID_LISTS:
            captured: list[ChangeEvent] = []
            monkeypatch.setattr(
                change_stream._change_hub,
                "emit",
                lambda lib, event: captured.append(event) or 1,
            )

            emit_change(
                "/lib/A.fichero",
                type="test.changed",
                **{name: [f"{name}-1"]},
            )

            assert len(captured) == 1, name
            event = captured[0]
            assert getattr(event, name) == [f"{name}-1"], name
            # every OTHER declared list stays empty -- one kind at a time
            for other in CHANGE_ID_LISTS:
                if other != name:
                    assert getattr(event, other) == [], (name, other)

            activity = _change_event_to_activity_response(event)
            assert json.loads(activity.metadata[name]) == [f"{name}-1"], name


class TestChangeSpecReachesSubscriber:
    @pytest.fixture
    def dummy_segment_action(self):
        """A throwaway action whose ChangeSpec carries segment_ids/pass_ids —
        this is the test that would have failed against the OLD hand-written
        keyword list in `_emit` (they were not in it at all)."""
        name = "test.dummy_segment_change"

        def _execute(db, params: BaseModel, ctx: ActionContext):
            return (
                {"ok": True},
                ChangeSpec(
                    domains=["test"],
                    emit_type="test.segment_changed",
                    segment_ids=["seg-1"],
                    pass_ids=["pass-1"],
                ),
            )

        class _Params(BaseModel):
            pass

        registry.register(
            ActionRegistration(
                name=name, params_model=_Params, execute=_execute,
                domains=["test"], undoable=False,
            )
        )
        yield name
        registry._actions.pop(name, None)

    def test_changespec_segment_and_pass_ids_reach_the_subscriber(
        self, db, dummy_segment_action, monkeypatch,
    ):
        """source.events.segment-ids."""
        captured: list[ChangeEvent] = []
        monkeypatch.setattr(
            "fichero_server.api.change_stream.emit_change",
            lambda *a, **k: captured.append(k),
        )
        ctx = ActionContext(actor="ui", library_path="/lib/test.fichero")
        registry.invoke(db, dummy_segment_action, {}, ctx)

        assert len(captured) == 1
        assert captured[0]["segment_ids"] == ["seg-1"]
        assert captured[0]["pass_ids"] == ["pass-1"]


class TestDeduplicationKeepsOrder:
    @pytest.mark.parametrize("list_name", ["segment_ids", "document_ids"])
    def test_dedupe_first_occurrence_wins_never_sorted(self, monkeypatch, list_name):
        """source.events.segment-ids. Ruled 2026-09-20: de-duplicated, order
        kept (first occurrence wins), never sorted -- for a NEW list
        (segment_ids) and an OLD one (document_ids), same rule."""
        captured: list[ChangeEvent] = []
        monkeypatch.setattr(
            change_stream._change_hub,
            "emit",
            lambda lib, event: captured.append(event) or 1,
        )

        emit_change("/lib/A.fichero", type="test.changed", **{list_name: ["b", "a", "b", "c"]})

        assert getattr(captured[0], list_name) == ["b", "a", "c"]


class TestOldEventStillDecodes:
    def test_event_with_neither_new_key_still_decodes(self):
        """source.events.segment-ids. An event serialised before this change
        (no segment_ids/pass_ids key) still decodes -- engine side."""
        old_shape = {"type": "entity.updated", "entity_ids": ["e1"]}
        event = ChangeEvent.model_validate(old_shape)
        assert event.segment_ids == []
        assert event.pass_ids == []


class TestSegmentIdsAloneDoNotPopulateDocumentIds:
    def test_only_segment_ids_set_leaves_document_ids_empty(self, monkeypatch):
        """source.events.segment-ids. The stream must not guess: a later
        slice decides to send both."""
        captured: list[ChangeEvent] = []
        monkeypatch.setattr(
            change_stream._change_hub,
            "emit",
            lambda lib, event: captured.append(event) or 1,
        )

        emit_change("/lib/A.fichero", type="test.changed", segment_ids=["seg-1"])

        assert captured[0].segment_ids == ["seg-1"]
        assert captured[0].document_ids == []


class TestNothingEmitsASegmentEventYet:
    def test_no_action_in_the_registry_emits_segment_or_pass_ids(self):
        """Stated plainly rather than invented: no segment action exists
        until slice 4, so nothing in the registry emits `segment.*`/`pass.*`
        events today. This test is the honest negative -- it will start
        failing (correctly) the day slice 4 registers one, which is the
        point at which this test should be deleted, not patched."""
        emitting_actions = [
            reg.name
            for reg in registry._actions.values()
            if reg.name.startswith(("segment.", "pass."))
        ]
        assert emitting_actions == []


class TestCrossLanguageContractFixture:
    """The engine half of the cross-language contract test (the build note's
    last bullet). The committed fixture is what the Swift side reads; the
    Swift-side decode test is the app lane's, not written here.

    Writing only happens under `FICHERO_REGENERATE_CONTRACT_FIXTURES=1`.
    A normal run COMPARES against the committed file and fails, naming the
    regenerate command, if it is stale -- it never rewrites it."""

    def test_fixture_matches_change_id_lists_or_says_how_to_regenerate(self):
        expected = _build_fixture_event().model_dump_json(indent=2) + "\n"

        if os.environ.get(_REGENERATE_ENV):
            FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
            FIXTURE_PATH.write_text(expected, encoding="utf-8")
            pytest.skip(f"regenerated {FIXTURE_PATH}")

        if not FIXTURE_PATH.exists():
            pytest.fail(f"{FIXTURE_PATH} is missing. Regenerate with:\n  {_REGENERATE_CMD}")

        actual = FIXTURE_PATH.read_text(encoding="utf-8")
        assert actual == expected, (
            "committed fixture is stale (CHANGE_ID_LISTS changed since it was "
            f"generated). Regenerate with:\n  {_REGENERATE_CMD}"
        )

        # Prove the fixture is exactly what a Swift decode test needs: every
        # declared list present and non-empty.
        written = json.loads(actual)
        for name in CHANGE_ID_LISTS:
            assert written[name], name
