"""Events a timeline can actually plot (#4667).

Daniel, 2026-09-04: "a workflow in Data Extract that extracts just EVENTS as
a TIMELINE, that we can put into a timeline dataset view."

The timeline (`KGTimelineView`) plots `KnowledgeClaim` rows carrying
`time_start` / `time_end`. Before this, only the date section produced those:
`_Event` has declared a `date` field all along and the two-stage rewrite
dropped it, so "extract events" produced entity rows with no time on them and
a timeline that showed nothing. These tests pin the whole path — the shipped
preset, the section filter that makes it "just events", and the date reaching
the claim.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.llm import LLMConfig
from fichero_server.llm.language_policy import parse_policy
from fichero_server.models import DocType, Document, FileType
from fichero_server.models.knowledge import EntityType, KnowledgeClaim
from fichero_server.workflows.default_workflows import _load_preset_files
from fichero_server.workflows.preset_manifest import (
    check_preset_manifest,
    load_manifest,
    load_shipped_presets,
)
from fichero_server.workflows.tools import extract_all
from fichero_server.workflows.tools import extract_svo_only as svo
from fichero_server.workflows.tools._entity_writer import upsert_entity
from fichero_server.workflows.tools.extract_entities_only import _requested_sections

PRESET_NAME = "Extract Events (Timeline)"
LEDGER = (
    Path(__file__).resolve().parents[3]
    / "src/fichero_server/resources/workflow_meta/preset_name_ledger.json"
)

# The verb and object below are spans OF this sentence: the grounding contract
# (#4666) rejects a predicate that is not on the page, and a fixture that
# ignored that would be testing a path the real run cannot take.
FIXTURE_TEXT = (
    "The signing of the fixture deed took place in Regression Place on "
    "10 April 1842, before the notary."
)


@pytest.fixture(autouse=True)
def _no_seeding(monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    monkeypatch.setattr(svo, "configured_policy", lambda: parse_policy(None))


class TestThePresetShips:
    def test_the_preset_is_shipped_in_the_extract_family(self):
        preset = next(p for p in _load_preset_files() if p["name"] == PRESET_NAME)
        assert preset["folder_path"] == "/Extract"
        assert "timeline" in preset["tags"]

    def test_its_name_is_in_the_ledger(self):
        # A preset id is uuid5(namespace, name): a name missing from the
        # ledger is a row nothing will ever retire.
        assert PRESET_NAME in json.loads(LEDGER.read_text())["names"]

    def test_the_version_manifest_is_current(self):
        assert check_preset_manifest(load_shipped_presets(), load_manifest()) == []

    def test_it_asks_for_events_and_dates_and_nothing_else(self):
        preset = next(p for p in _load_preset_files() if p["name"] == PRESET_NAME)
        configs = {node["id"]: node.get("config") or {} for node in preset["nodes"]}
        assert configs["extract-events"]["entity_types"] == "events"
        # Dates are the time axis. A timeline preset that quietly dropped them
        # would render a chart with nothing to plot against.
        assert _requested_sections(
            configs["extract-event-claims"]["entity_types"]
        ) == {"events", "dates"}


class TestSectionFilter:
    def test_all_is_the_default_so_every_existing_preset_is_unchanged(self):
        assert _requested_sections(None) == _requested_sections("all")
        assert "people" in _requested_sections(None)

    def test_an_unknown_section_name_does_not_empty_the_run(self):
        # Better to run every section than to silently extract nothing.
        assert "people" in _requested_sections("bogus")


class TestEventsReachTheTimeline:
    def _library(self, tmp_path: Path, name: str):
        library_path = tmp_path / f"{name}.fichero"
        seed(library_path)
        db = db_manager.get_database(library_path)
        db.save(
            Document(
                id="d1",
                name="fixture.txt",
                doc_type=DocType.file,
                file_type=FileType.text,
                page_content=FIXTURE_TEXT,
            )
        )
        return library_path, db

    def _run(self, library_path, entity_types):
        return asyncio.run(
            svo.extract_svo_only(
                {"documents": [{"id": "d1"}], "entity_types": entity_types},
                {
                    "library_path": str(library_path),
                    "selected_doc_ids": ["d1"],
                    "task_id": "events-timeline-test",
                },
                LLMConfig(provider="fake", model="fake-model"),
            )
        )

    def test_an_event_claim_lands_with_a_temporal_scope(self, tmp_path, monkeypatch):
        library_path, db = self._library(tmp_path, "events")
        upsert_entity(
            db,
            canonical_name="The signing of the fixture deed",
            entity_type=EntityType.event,
            source_document_id="d1",
        )

        async def fake_structured(**kwargs):
            schema = kwargs["schema"]
            if getattr(schema, "__name__", "") == "_Section_Dates":
                return schema(items=[])
            return schema(
                subject="The signing of the fixture deed",
                claims=[
                    {
                        "subject": "The signing of the fixture deed",
                        "verb": "took place",
                        "object": "in Regression Place",
                        "source_text": "took place in Regression Place",
                        "date": "1842-04-10",
                    }
                ],
            )

        # Both bindings: the dates pass calls through `extract_svo_only`, the
        # per-entity claim loop through `extract_all`. Patching one leaves the
        # other reaching a real provider.
        monkeypatch.setattr(svo, "chat_structured_with_fallback", fake_structured)
        monkeypatch.setattr(
            extract_all, "chat_structured_with_fallback", fake_structured
        )
        self._run(library_path, "events,dates")

        claims = [
            c
            for c in db.query(KnowledgeClaim, source_document_id="d1")
            if "took place" in (c.text or "")
        ]
        assert claims, "the event claim was not written"
        claim = claims[0]
        assert claim.time_start == "1842-04-10"
        assert claim.time_end == "1842-04-10"
        assert claim.time_precision == "day"

    def test_an_undated_event_is_still_a_claim_just_not_a_timeline_row(
        self, tmp_path, monkeypatch
    ):
        # An inferred date would be a guess wearing a fact's clothes. Absent
        # is the honest answer, and the claim still belongs in the graph.
        library_path, db = self._library(tmp_path, "undated")
        upsert_entity(
            db,
            canonical_name="The signing of the fixture deed",
            entity_type=EntityType.event,
            source_document_id="d1",
        )

        async def fake_structured(**kwargs):
            schema = kwargs["schema"]
            if getattr(schema, "__name__", "") == "_Section_Dates":
                return schema(items=[])
            return schema(
                subject="The signing of the fixture deed",
                claims=[
                    {
                        "subject": "The signing of the fixture deed",
                        "verb": "took place",
                        "object": "before the notary",
                        "source_text": "before the notary",
                        "date": "",
                    }
                ],
            )

        # Both bindings: the dates pass calls through `extract_svo_only`, the
        # per-entity claim loop through `extract_all`. Patching one leaves the
        # other reaching a real provider.
        monkeypatch.setattr(svo, "chat_structured_with_fallback", fake_structured)
        monkeypatch.setattr(
            extract_all, "chat_structured_with_fallback", fake_structured
        )
        self._run(library_path, "events,dates")

        claims = [
            c
            for c in db.query(KnowledgeClaim, source_document_id="d1")
            if "took place" in (c.text or "")
        ]
        assert claims
        assert claims[0].time_start is None

    def test_asking_for_events_does_not_run_the_people_loop(
        self, tmp_path, monkeypatch
    ):
        library_path, db = self._library(tmp_path, "scoped")
        upsert_entity(
            db,
            canonical_name="The notary",
            entity_type=EntityType.person,
            source_document_id="d1",
        )
        asked: list[str] = []

        async def fake_structured(**kwargs):
            schema = kwargs["schema"]
            asked.append(getattr(schema, "__name__", ""))
            if getattr(schema, "__name__", "") == "_Section_Dates":
                return schema(items=[])
            return schema(subject="x", claims=[])

        # Both bindings: the dates pass calls through `extract_svo_only`, the
        # per-entity claim loop through `extract_all`. Patching one leaves the
        # other reaching a real provider.
        monkeypatch.setattr(svo, "chat_structured_with_fallback", fake_structured)
        monkeypatch.setattr(
            extract_all, "chat_structured_with_fallback", fake_structured
        )
        result = self._run(library_path, "events,dates")

        # The person on the page is never asked about: that is what makes this
        # preset cheaper than a full extraction, not just narrower.
        assert result["summary"]["entities_processed"] == 0
        assert asked == ["_Section_Dates"]
