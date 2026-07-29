"""Tests for the ChangeEvent contract guardrail (#4211).

`ChangeEvent` is the one engine<->app boundary with no codegen backstop — SSE
bodies cannot be modelled as response schemas, so the Swift side is
hand-written and a divergence is silent. The guardrail is the backstop; these
are the guardrail's backstop.

Both directions are exercised with synthetic sources, because a check whose
failure path has never been observed is indistinguishable from a broken one —
and this check's entire job is catching a silence.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "check_change_event_contract.py"


def _load():
    spec = importlib.util.spec_from_file_location("_change_event_contract", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load()

_PY = '''
from pydantic import BaseModel, Field


class ChangeEvent(BaseModel):
    type: str
    entity_ids: list[str] = Field(default_factory=list)
    run_id: str | None = None
'''

_SWIFT = """
struct ChangeEvent: Decodable, Sendable {
    let type: String
    let entityIds: [String]
    let runId: String?

    enum CodingKeys: String, CodingKey {
        case type
        case entityIds = "entity_ids"
        case runId = "run_id"
    }
}
"""


def _sources(tmp_path: Path, python: str = _PY, swift: str = _SWIFT):
    py = tmp_path / "change_stream.py"
    sw = tmp_path / "LibraryChangeStream.swift"
    py.write_text(python, encoding="utf-8")
    sw.write_text(swift, encoding="utf-8")
    return py, sw


class TestParsing:
    def test_python_fields_are_read_from_the_class(self, tmp_path):
        py, _ = _sources(tmp_path)

        assert guard.python_fields(py) == {"type", "entity_ids", "run_id"}

    def test_swift_wire_names_come_from_coding_keys(self, tmp_path):
        """The WIRE name, not the Swift property name — `entityIds` is irrelevant."""
        _, sw = _sources(tmp_path)

        assert guard.swift_wire_keys(sw) == {"type", "entity_ids", "run_id"}

    def test_a_bare_case_uses_the_property_name_as_the_wire_name(self, tmp_path):
        """`case actor` with no `=` means the wire name is `actor`."""
        _, sw = _sources(
            tmp_path,
            swift=_SWIFT.replace("        case type\n", "        case type\n        case actor\n"),
        )

        assert "actor" in guard.swift_wire_keys(sw)

    def test_renaming_a_swift_PROPERTY_does_not_trip_the_check(self, tmp_path):
        """Anchored at the contract, not the implementation.

        The stranded 0345f4208 test pinned implementation text and died on a
        refactor that improved the thing it guarded. Renaming the Swift
        property while keeping the wire name must be invisible here.
        """
        _, sw = _sources(tmp_path, swift=_SWIFT.replace("entityIds", "touchedEntityIdentifiers"))

        assert guard.swift_wire_keys(sw) == {"type", "entity_ids", "run_id"}


class TestItParsesTheRightType:
    """Closing a limit whose failure direction was a silent PASS (#4211)."""

    def test_a_decodable_declared_ABOVE_change_event_is_not_parsed(self, tmp_path):
        """Previously the FIRST CodingKeys in the file won — wrong type, still green."""
        decoy = """
struct SomethingElse: Decodable {
    let other: String

    enum CodingKeys: String, CodingKey {
        case other = "totally_different"
    }
}
"""
        _, sw = _sources(tmp_path, swift=decoy + _SWIFT)

        keys = guard.swift_wire_keys(sw)

        assert "totally_different" not in keys, "parsed the decoy type's keys"
        assert keys == {"type", "entity_ids", "run_id"}

    def test_a_type_declared_BETWEEN_the_struct_and_its_keys_is_refused(self, tmp_path):
        """Ambiguous rather than wrong: fail loudly instead of guessing."""
        import pytest

        broken = _SWIFT.replace(
            "    enum CodingKeys",
            "    struct Nested: Decodable { let x: String }\n\n    enum CodingKeys",
        )
        _, sw = _sources(tmp_path, swift=broken)

        with pytest.raises(SystemExit, match="Nested"):
            guard.swift_wire_keys(sw)

    def test_a_missing_change_event_struct_is_refused(self, tmp_path):
        """A renamed/moved struct must fail loudly, not silently compare nothing."""
        import pytest

        _, sw = _sources(tmp_path, swift=_SWIFT.replace("struct ChangeEvent", "struct Renamed"))

        with pytest.raises(SystemExit, match="ChangeEvent"):
            guard.swift_wire_keys(sw)


class TestTheDangerousDirection:
    """Swift decoding a field the engine does not send — silent nil."""

    def test_a_swift_key_with_no_engine_field_is_detected(self, tmp_path):
        py, sw = _sources(
            tmp_path,
            swift=_SWIFT.replace(
                '        case runId = "run_id"\n',
                '        case runId = "run_id"\n        case ghost = "ghost_field"\n',
            ),
        )

        undelivered = guard.swift_wire_keys(sw) - guard.python_fields(py)

        assert undelivered == {"ghost_field"}

    def test_a_renamed_engine_field_is_detected(self, tmp_path):
        """The realistic case: the engine renames, the client is not updated."""
        py, sw = _sources(tmp_path, python=_PY.replace("run_id", "run_identifier"))

        undelivered = guard.swift_wire_keys(sw) - guard.python_fields(py)

        assert "run_id" in undelivered


class TestTheReviewableDirection:
    """Engine fields the client ignores — usually fine, but must be declared."""

    def test_an_engine_only_field_is_surfaced(self, tmp_path):
        py, sw = _sources(
            tmp_path, python=_PY.replace("    run_id:", "    brand_new: str | None = None\n    run_id:")
        )

        unconsumed = guard.python_fields(py) - guard.swift_wire_keys(sw)

        assert "brand_new" in unconsumed


class TestTheRealRepoIsGreen:
    def test_the_shipped_contract_agrees(self):
        undelivered, unconsumed = guard.scan()

        assert not undelivered, f"client decodes fields the engine never sends: {undelivered}"
        assert not (unconsumed - set(guard.ENGINE_ONLY_FIELDS)), (
            f"undeclared engine-only fields: {unconsumed - set(guard.ENGINE_ONLY_FIELDS)}"
        )

    def test_no_declared_exemption_is_stale(self):
        """Same self-shrinking property as the other baselines."""
        _undelivered, unconsumed = guard.scan()
        stale = set(guard.ENGINE_ONLY_FIELDS) - unconsumed

        assert not stale, f"ENGINE_ONLY_FIELDS entries that no longer apply: {stale}"

    def test_every_exemption_states_a_reason(self):
        """An unexplained entry is indistinguishable from an oversight."""
        for field, reason in guard.ENGINE_ONLY_FIELDS.items():
            assert len(reason.strip()) > 20, f"{field} needs a real reason, got {reason!r}"

    def test_document_parents_is_flagged_as_client_work_not_bookkeeping(self):
        """It is exempted TODAY but the client should consume it (#4205).

        Pinning this stops the entry being read as settled bookkeeping and
        quietly living forever alongside the replay fields.
        """
        reason = guard.ENGINE_ONLY_FIELDS["document_parents"]

        assert "#4205" in reason
        assert "SHOULD consume" in reason
        assert "NEVER 'root'" in reason
