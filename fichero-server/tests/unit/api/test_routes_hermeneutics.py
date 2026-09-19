"""Tests for hermeneutics routes.

Hermeneutics manages interpretive frameworks (historical, disciplinary,
thematic…) and their application to claims via Interpretations and
Patterns. Routes live at /api/hermeneutics/... (router has no prefix,
mounted at "/api/hermeneutics").
"""

from fichero_server.models import KnowledgeClaim
from fichero_server.models.hermeneutics import (
    FrameworkType,
    InterpretiveActType,
    InterpretiveFramework,
    Interpretation,
)


BASE = "/api/hermeneutics"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_framework(fwk_id: str = "fwk-1", name: str = "Marxist Lens") -> InterpretiveFramework:
    return InterpretiveFramework(
        id=fwk_id,
        name=name,
        framework_type=FrameworkType.theoretical,
        description="Materialist analysis of history",
    )


def _make_interpretation(
    interp_id: str = "interp-1",
    framework_id: str = "fwk-1",
) -> Interpretation:
    return Interpretation(
        id=interp_id,
        framework_id=framework_id,
        interpretation_text="Labor conditions reflect class struggle.",
        act=InterpretiveActType.contextualizing,
    )


# ---------------------------------------------------------------------------
# POST /api/hermeneutics/frameworks
# ---------------------------------------------------------------------------


class TestCreateFramework:
    def test_create_framework(self, client):
        r = client.post(f"{BASE}/frameworks", json={
            "name": "Postcolonial Theory",
            "framework_type": "theoretical",
            "description": "Examines colonial legacies.",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Postcolonial Theory"
        assert "id" in data


# ---------------------------------------------------------------------------
# GET /api/hermeneutics/frameworks
# ---------------------------------------------------------------------------


class TestListFrameworks:
    def test_empty_list(self, client):
        r = client.get(f"{BASE}/frameworks")
        assert r.status_code == 200
        assert r.json() == {"items": [], "count": 0}

    def test_returns_frameworks(self, client, db):
        db.save(_make_framework("fwk-1", "Framework A"))
        db.save(_make_framework("fwk-2", "Framework B"))

        r = client.get(f"{BASE}/frameworks")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2


# ---------------------------------------------------------------------------
# GET /api/hermeneutics/frameworks/{id}
# ---------------------------------------------------------------------------


class TestGetFramework:
    def test_get_existing(self, client, db):
        db.save(_make_framework("fwk-get", "Named Framework"))

        r = client.get(f"{BASE}/frameworks/fwk-get")
        assert r.status_code == 200
        assert r.json()["name"] == "Named Framework"

    def test_get_missing_returns_404(self, client):
        r = client.get(f"{BASE}/frameworks/no-such")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/hermeneutics/frameworks/{id}
# ---------------------------------------------------------------------------


class TestUpdateFramework:
    def test_update_description(self, client, db):
        db.save(_make_framework("fwk-upd", "Updatable"))

        r = client.patch(f"{BASE}/frameworks/fwk-upd", json={
            "description": "Updated description."
        })
        assert r.status_code == 200
        assert r.json()["description"] == "Updated description."

    def test_update_missing_returns_404(self, client):
        r = client.patch(f"{BASE}/frameworks/no-such", json={"description": "X"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/hermeneutics/frameworks/{id}
# ---------------------------------------------------------------------------


class TestDeleteFramework:
    def test_delete_framework(self, client, db):
        db.save(_make_framework("fwk-del", "To Delete"))

        r = client.delete(f"{BASE}/frameworks/fwk-del")
        assert r.status_code == 200

    def test_delete_missing_returns_404(self, client):
        r = client.delete(f"{BASE}/frameworks/no-such")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/hermeneutics/interpretations
# ---------------------------------------------------------------------------


class TestCreateInterpretation:
    def test_create_interpretation(self, client, db):
        db.save(_make_framework("fwk-int"))
        db.save(KnowledgeClaim(id="claim-int-1", text="c", source_document_id="d", entity_ids=[]))

        r = client.post(f"{BASE}/interpretations", json={
            "framework_id": "fwk-int",
            "claim_id": "claim-int-1",
            "passage_text": "Workers organized in the factories.",
            "interpretation_text": "This evidence shows class conflict.",
            "act": "contextualizing",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["framework_id"] == "fwk-int"

    def test_create_interpretation_populates_predicate_canonical(self, client, db):
        db.save(_make_framework("fwk-int-pred"))
        db.save(KnowledgeClaim(id="claim-int-pred-1", text="c", source_document_id="d", entity_ids=[]))

        r = client.post(f"{BASE}/interpretations", json={
            "framework_id": "fwk-int-pred",
            "claim_id": "claim-int-pred-1",
            "passage_text": "The reading foregrounds labor.",
            "interpretation_text": "This reading foregrounds labor history.",
            "act": "contextualizing",
            "predicate": "foregrounds",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["predicate"] == "foregrounds"
        assert data["predicate_canonical"] == "foregrounds"

    def test_missing_framework_returns_404(self, client):
        r = client.post(f"{BASE}/interpretations", json={
            "framework_id": "no-such-framework",
            "interpretation_text": "Some text.",
            "act": "reading",
        })
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/hermeneutics/interpretations
# ---------------------------------------------------------------------------


class TestListInterpretations:
    def test_empty_list(self, client):
        r = client.get(f"{BASE}/interpretations")
        assert r.status_code == 200
        assert r.json() == {"items": [], "count": 0}

    def test_returns_interpretations(self, client, db):
        db.save(_make_framework("fwk-li"))
        db.save(_make_interpretation("i-1", "fwk-li"))
        db.save(_make_interpretation("i-2", "fwk-li"))

        r = client.get(f"{BASE}/interpretations")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2

    def test_update_interpretation_updates_predicate_canonical(self, client, db):
        db.save(_make_framework("fwk-upd"))
        interp = _make_interpretation("i-upd", "fwk-upd")
        db.save(interp)

        r = client.patch(f"{BASE}/interpretations/{interp.id}", json={
            "predicate": "contests reading",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["predicate"] == "contests reading"
        assert data["predicate_canonical"] == "contests_reading"


# ---------------------------------------------------------------------------
# Deterministic list ordering (team-lead review): `db.all(Model)` is storage
# order, not a contract, and the app splices new interpretations in place
# assuming oldest-first. Every list route in hermeneutics.py shares the
# same fix (`_ordered`): created_at ascending, id as a stable tiebreak.
# ---------------------------------------------------------------------------


from datetime import datetime, timedelta, timezone  # noqa: E402

from fichero_server.models.hermeneutics import (  # noqa: E402
    CircleNavigationDirection,
    HermeneuticCircleState,
    PatternInstance,
)


def _make_pattern(pattern_id: str, created_at: datetime) -> PatternInstance:
    return PatternInstance(
        id=pattern_id,
        name="A pattern",
        description="A recurring structure.",
        pattern_type="thematic",
        created_at=created_at,
        updated_at=created_at,
    )


def _make_circle_state(state_id: str, created_at: datetime) -> HermeneuticCircleState:
    return HermeneuticCircleState(
        id=state_id,
        claim_id="claim-1",
        current_focus="part",
        focus_id="focus-1",
        focus_label="A focus",
        direction=CircleNavigationDirection.part_to_whole,
        created_at=created_at,
        updated_at=created_at,
    )


class TestListOrderingIsDeterministic:
    """Rows inserted out of order come back created_at-ascending; equal
    timestamps (or a legacy row with none) are broken by id, stably."""

    def test_interpretations_come_back_oldest_first_regardless_of_insert_order(
        self, client, db
    ):
        db.save(_make_framework("fwk-order"))
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        newest = _make_interpretation("interp-newest", "fwk-order")
        newest.created_at = t0 + timedelta(days=2)
        oldest = _make_interpretation("interp-oldest", "fwk-order")
        oldest.created_at = t0
        middle = _make_interpretation("interp-middle", "fwk-order")
        middle.created_at = t0 + timedelta(days=1)
        # Saved newest -> oldest -> middle: storage order is NOT the
        # expected response order, which is the whole point of the test.
        db.save(newest)
        db.save(oldest)
        db.save(middle)

        r = client.get(f"{BASE}/interpretations")

        assert r.status_code == 200
        ids = [item["id"] for item in r.json()["items"]]
        assert ids == ["interp-oldest", "interp-middle", "interp-newest"]

    def test_interpretations_with_equal_timestamps_break_ties_by_id_stably(
        self, client, db
    ):
        db.save(_make_framework("fwk-tie"))
        tied_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        b = _make_interpretation("interp-b", "fwk-tie")
        b.created_at = tied_at
        a = _make_interpretation("interp-a", "fwk-tie")
        a.created_at = tied_at
        db.save(b)
        db.save(a)

        r1 = client.get(f"{BASE}/interpretations")
        r2 = client.get(f"{BASE}/interpretations")

        ids1 = [item["id"] for item in r1.json()["items"]]
        ids2 = [item["id"] for item in r2.json()["items"]]
        assert ids1 == ["interp-a", "interp-b"]  # id-order tiebreak
        assert ids1 == ids2  # stable across repeated calls

    def test_frameworks_come_back_oldest_first(self, client, db):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        newer = _make_framework("fwk-newer", "Newer")
        newer.created_at = t0 + timedelta(days=1)
        older = _make_framework("fwk-older", "Older")
        older.created_at = t0
        db.save(newer)
        db.save(older)

        r = client.get(f"{BASE}/frameworks")

        ids = [item["id"] for item in r.json()["items"]]
        assert ids == ["fwk-older", "fwk-newer"]

    def test_patterns_come_back_oldest_first(self, client, db):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        db.save(_make_pattern("pattern-newer", t0 + timedelta(days=1)))
        db.save(_make_pattern("pattern-older", t0))

        r = client.get(f"{BASE}/patterns")

        ids = [item["id"] for item in r.json()["items"]]
        assert ids == ["pattern-older", "pattern-newer"]

    def test_circle_states_come_back_oldest_first(self, client, db):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        db.save(_make_circle_state("state-newer", t0 + timedelta(days=1)))
        db.save(_make_circle_state("state-older", t0))

        r = client.get(f"{BASE}/circle-state")

        ids = [item["id"] for item in r.json()["items"]]
        assert ids == ["state-older", "state-newer"]


# ---------------------------------------------------------------------------
# GET /api/hermeneutics/taxonomy/methods  (#1126 — merged from kg_interpretations)
# ---------------------------------------------------------------------------


class TestTaxonomyMethods:
    def test_returns_acts_and_frameworks(self, client):
        r = client.get(f"{BASE}/taxonomy/methods")
        assert r.status_code == 200
        data = r.json()
        assert "acts" in data
        assert "frameworks" in data
        assert len(data["acts"]) > 0
        assert len(data["frameworks"]) > 0
        # Spot-check structure
        act = data["acts"][0]
        assert "value" in act and "label" in act


# ---------------------------------------------------------------------------
# The /api/kg/interpretations/* alias mount (#1126) was deleted in the
# 2026-07-27 endpoint cleanup — same router, second mount, 13 duplicate spec
# paths with zero callers. /api/hermeneutics/* (tested above) is the ONE URL.
# ---------------------------------------------------------------------------


class TestKgInterpretationsAliasIsGone:
    def test_alias_mount_no_longer_exists(self, client):
        assert client.get("/api/kg/interpretations/frameworks").status_code == 404
