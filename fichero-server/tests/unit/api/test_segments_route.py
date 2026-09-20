"""GET /api/segments/document/{doc_id} — source-model slice 1 (read-only).

Spec: docs/contributor_manual/specs/source/source-model.md, "Slice 1 — one
way to read a source's segments". Each test names the behaviour id it pins.
This slice writes nothing; there is no undo, no action, no audit row.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, Document, DocType, FileType, Status
from fichero_server.security import accounts, authz

pytestmark = pytest.mark.source_model


def _make_doc(db, name: str = "page.jpg") -> Document:
    doc = Document(
        name=name,
        doc_type=DocType.file,
        file_type=FileType.image,
        path=f"/path/{name}",
        status=Status.completed,
    )
    db.save(doc)
    return doc


def _make_regions_artifact(db, doc_id: str, boxes=None, **artifact_kwargs) -> Artifact:
    # `provider` (and `model`, when given) describe the ARTIFACT, and
    # provenance_kind is derived from the Artifact's own fields (route:
    # `segments_from_result(..., provider=artifact.provider, ...)`) — so it
    # must reach BOTH the geometry result and the Artifact record, the way
    # a real workflow tool sets both. Only `rendition_id` is geometry-only.
    provider = artifact_kwargs.setdefault("provider", "apple_vision")
    geometry = OCRGeometryResult(
        text="alpha beta gamma",
        provider=provider or "",
        rendition_id=artifact_kwargs.pop("rendition_id", None),
        boxes=boxes
        if boxes is not None
        else [
            OCRGeometryBox(
                text="alpha", bbox=[0.1, 0.1, 0.2, 0.05], level="region",
                char_start=0, char_end=5,
            ),
            OCRGeometryBox(
                text="beta", bbox=[0.1, 0.3, 0.2, 0.05], level="line",
                char_start=6, char_end=10,
            ),
        ],
    )
    artifact = Artifact(
        document_id=doc_id,
        artifact_type="regions",
        content="alpha beta gamma",
        ocr_geometry=geometry,
        **artifact_kwargs,
    )
    db.save(artifact)
    return artifact


def _get(client, doc_id: str, **params):
    return client.get(f"/api/segments/document/{doc_id}", params=params)


# ---------------------------------------------------------------------------
# Multi-user fixtures — same shape as test_routes_search.py's, so the
# denied-viewer behaviour is pinned the same way across routes.
# ---------------------------------------------------------------------------


@pytest.fixture
def users(app_db):
    owner = app_db.create_user(
        username="owner", display_name="Owner",
        password_hash=accounts.hash_password("password"), is_owner=True,
    )
    viewer = app_db.create_user(
        username="viewer", display_name="Viewer",
        password_hash=accounts.hash_password("password"),
    )
    return SimpleNamespace(owner=owner, viewer=viewer)


def _grant(app_db, user, library_path: str, role: str) -> None:
    app_db.set_library_role(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        role=role,
    )


@pytest.fixture
def multiuser_client(test_package, app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")

    import fichero_server.api.main as api_main

    api_main = importlib.reload(api_main)
    client = TestClient(
        api_main.app,
        headers={"X-Fichero-Library-Path": quote(str(test_package), safe="/")},
    )

    def _login(username: str) -> dict[str, str]:
        response = client.post(
            "/api/auth/login", json={"username": username, "password": "password"},
        )
        assert response.status_code == 200
        token = response.json()["session_token"]
        return {"Authorization": f"Bearer {token}"}

    try:
        yield client, _login, str(test_package)
    finally:
        client.close()
        api_main.app.dependency_overrides.clear()
        monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
        importlib.reload(api_main)


class TestReadEitherStore:
    def test_one_provisional_segment_per_box_rect_for_rect(self, client, db):
        """source.seam.read-either-store, source.one-store (engine half)."""
        doc = _make_doc(db)
        artifact = _make_regions_artifact(db, doc.id)

        r = _get(client, doc.id)
        assert r.status_code == 200
        body = r.json()
        assert body["document_id"] == doc.id
        assert len(body["segments"]) == 2
        for index, (box, segment) in enumerate(
            zip(artifact.ocr_geometry.boxes, body["segments"])
        ):
            assert segment["provisional"] is True
            assert segment["id"] == f"legacy:{artifact.id}:{index}"
            # None until a tool records its own label; nothing writes it yet.
            assert segment["kind_raw"] is None
            assert segment["anchor"]["rect"] == box.bbox
            assert segment["text"] == box.text

    def test_document_with_no_geometry_returns_empty_list_not_an_error(self, client, db):
        doc = _make_doc(db)
        r = _get(client, doc.id)
        assert r.status_code == 200
        assert r.json() == {"document_id": doc.id, "passes": [], "segments": []}

    def test_unknown_document_404s(self, client, db):
        r = _get(client, "no-such-doc")
        assert r.status_code == 404


class TestNamesItsImage:
    def test_every_segment_names_the_results_rendition(self, client, db):
        """source.segment.names-its-image."""
        doc = _make_doc(db)
        _make_regions_artifact(db, doc.id, rendition_id="rendition-xyz")
        body = _get(client, doc.id).json()
        assert body["segments"], "fixture must produce at least one segment"
        for segment in body["segments"]:
            assert segment["anchor"]["rendition_id"] == "rendition-xyz"


def _table_names(db) -> set[str]:
    return {t[0] for t in db.conn.execute("SHOW TABLES").fetchall()}


def _table_row_counts(db) -> dict[str, int]:
    tables = [t[0] for t in db.conn.execute("SHOW TABLES").fetchall()]
    return {t: db.conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}


class TestOpeningWritesNothing:
    def test_reading_twice_writes_nothing(self, client, db):
        """The 'opening a page writes nothing' half of
        source.store.ids-on-first-edit. Pinned wide, not just version/audit
        count: every table's row count, and the document's and artifact's
        full JSON, before and after two reads. Strong form restored (#4921
        review): `Segment`/`SegmentPass` are registered in
        `Database._all_schema_models()`, so their tables exist (empty) from
        the moment this library opened -- a read has nothing left to create,
        so reading twice changes neither the table LIST nor any row count."""
        doc = _make_doc(db)
        artifact = _make_regions_artifact(db, doc.id)

        before_tables = _table_names(db)
        before_counts = _table_row_counts(db)
        before_doc = db.get(Document, doc.id).model_dump(mode="json")
        before_artifact = db.get(Artifact, artifact.id).model_dump(mode="json")

        _get(client, doc.id)
        _get(client, doc.id)

        assert _table_names(db) == before_tables
        assert _table_row_counts(db) == before_counts
        assert db.get(Document, doc.id).model_dump(mode="json") == before_doc
        assert db.get(Artifact, artifact.id).model_dump(mode="json") == before_artifact


class TestKrakenPolygonAndBaseline:
    def test_polygon_and_baseline_normalize_from_pixel_frame(self, client, db):
        """'Kraken's polygon and baseline' — normalised to the named image;
        a box with none returns none."""
        doc = _make_doc(db)
        boxes = [
            OCRGeometryBox(
                text="",
                bbox=[0.0, 0.0, 0.5, 0.1],
                level="line",
                provider="kraken",
                source="kraken-blla",
                metadata={
                    "polygon_px": [[0, 0], [500, 0], [500, 100], [0, 100]],
                    "baseline_px": [[0, 90], [500, 90]],
                    "pixel_frame": {"width": 1000, "height": 1000},
                },
            ),
            OCRGeometryBox(text="plain", bbox=[0.1, 0.1, 0.2, 0.05], level="word"),
        ]
        _make_regions_artifact(db, doc.id, boxes=boxes, provider="kraken")

        body = _get(client, doc.id).json()
        kraken_segment, plain_segment = body["segments"]
        assert kraken_segment["anchor"]["polygon"] == [
            [0.0, 0.0], [0.5, 0.0], [0.5, 0.1], [0.0, 0.1],
        ]
        assert kraken_segment["baseline"] == [[0.0, 0.09], [0.5, 0.09]]
        # Raw pixel values kept, not thrown away -- but NOT on the anchor
        # (fix 3): the anchor is what slices 3/6 store, so it stays clean.
        assert kraken_segment["metadata"]["raw_pixel_frame"] == {"width": 1000, "height": 1000}
        assert "raw_pixel_frame" not in kraken_segment["anchor"]

        assert plain_segment["anchor"].get("polygon") is None
        assert plain_segment["baseline"] is None
        assert plain_segment["metadata"] == {}


class TestOneBadBoxNeverFailsThePage:
    """`source.seam.read-either-store`: a box the anchor cannot hold is
    still returned as a segment (fix 1) -- never a 500 for the whole page."""

    @pytest.mark.parametrize(
        "box, expect_rect_unset",
        [
            pytest.param(
                OCRGeometryBox(text="zero-width", bbox=[0.1, 0.1, 0.0, 0.05], level="word"),
                True,
                id="zero-width",
            ),
            pytest.param(
                OCRGeometryBox(text="zero-height", bbox=[0.1, 0.1, 0.2, 0.0], level="word"),
                True,
                id="zero-height",
            ),
        ],
    )
    def test_degenerate_bbox_still_returns_a_segment(self, client, db, box, expect_rect_unset):
        doc = _make_doc(db)
        _make_regions_artifact(db, doc.id, boxes=[box])

        r = _get(client, doc.id)
        assert r.status_code == 200
        segments = r.json()["segments"]
        assert len(segments) == 1
        assert segments[0]["anchor"]["rect"] is None
        assert "geometry_problem" in segments[0]["metadata"]

    def test_polygon_point_outside_its_pixel_frame_still_returns_a_segment(self, client, db):
        doc = _make_doc(db)
        box = OCRGeometryBox(
            text="off-frame",
            bbox=[0.1, 0.1, 0.2, 0.05],
            level="line",
            metadata={
                # x=1010 is outside a 1000-wide frame.
                "polygon_px": [[0, 0], [1010, 0], [1010, 100], [0, 100]],
                "pixel_frame": {"width": 1000, "height": 1000},
            },
        )
        _make_regions_artifact(db, doc.id, boxes=[box])

        r = _get(client, doc.id)
        assert r.status_code == 200
        segment = r.json()["segments"][0]
        # The rect (well formed) survives; only the polygon is dropped.
        assert segment["anchor"]["rect"] == [0.1, 0.1, 0.2, 0.05]
        assert segment["anchor"].get("polygon") is None
        assert "geometry_problem" in segment["metadata"]

    def test_two_point_polygon_still_returns_a_segment(self, client, db):
        doc = _make_doc(db)
        box = OCRGeometryBox(
            text="two-points",
            bbox=[0.1, 0.1, 0.2, 0.05],
            level="line",
            metadata={
                "polygon_px": [[0, 0], [100, 0]],
                "pixel_frame": {"width": 1000, "height": 1000},
            },
        )
        _make_regions_artifact(db, doc.id, boxes=[box])

        r = _get(client, doc.id)
        assert r.status_code == 200
        segment = r.json()["segments"][0]
        assert segment["anchor"]["rect"] == [0.1, 0.1, 0.2, 0.05]
        assert segment["anchor"].get("polygon") is None
        assert "geometry_problem" in segment["metadata"]

    def test_one_bad_box_does_not_fail_the_others_on_the_same_page(self, client, db):
        good = OCRGeometryBox(text="good", bbox=[0.1, 0.1, 0.2, 0.05], level="word")
        bad = OCRGeometryBox(text="bad", bbox=[0.5, 0.5, 0.0, 0.1], level="word")
        doc = _make_doc(db)
        _make_regions_artifact(db, doc.id, boxes=[good, bad])

        r = _get(client, doc.id)
        assert r.status_code == 200
        segments = r.json()["segments"]
        assert len(segments) == 2
        assert segments[0]["anchor"]["rect"] == [0.1, 0.1, 0.2, 0.05]
        assert "geometry_problem" not in segments[0]["metadata"]
        assert segments[1]["anchor"]["rect"] is None
        assert "geometry_problem" in segments[1]["metadata"]

    def test_bad_rect_does_not_swallow_a_good_polygon(self, client, db):
        """Re-review fix (1): the docstring said a bad rect never swallows
        a good polygon; it did, because there was no polygon-only attempt."""
        doc = _make_doc(db)
        box = OCRGeometryBox(
            text="zero-height-good-polygon",
            bbox=[0.1, 0.1, 0.2, 0.0],  # zero height: rect is bad
            level="line",
            metadata={
                "polygon_px": [[0, 0], [500, 0], [500, 100], [0, 100]],
                "pixel_frame": {"width": 1000, "height": 1000},
            },
        )
        _make_regions_artifact(db, doc.id, boxes=[box])

        segment = _get(client, doc.id).json()["segments"][0]
        assert segment["anchor"]["rect"] is None
        assert segment["anchor"]["polygon"] == [
            [0.0, 0.0], [0.5, 0.0], [0.5, 0.1], [0.0, 0.1],
        ]
        assert "geometry_problem" in segment["metadata"]

    @pytest.mark.parametrize(
        "metadata, why",
        [
            pytest.param(
                {"polygon_px": [[0, 0], [500, 0], [500, 100]]},
                "missing pixel_frame",
                id="missing-pixel-frame",
            ),
            pytest.param(
                {
                    "polygon_px": [[0, 0], [500, 0], [500, 100]],
                    "pixel_frame": {"width": 0, "height": 1000},
                },
                "zero pixel_frame",
                id="zero-pixel-frame",
            ),
            pytest.param(
                {
                    "polygon_px": [[0, 0], [500, 0], [500, 100]],
                    "pixel_frame": "not a dict",
                },
                "pixel_frame is a string",
                id="string-pixel-frame",
            ),
            pytest.param(
                {
                    "polygon_px": [["a", "b"], [500, 0], [500, 100]],
                    "pixel_frame": {"width": 1000, "height": 1000},
                },
                "non-numeric points",
                id="non-numeric-points",
            ),
        ],
    )
    def test_unnormalizable_polygon_is_reported_not_silently_dropped(
        self, client, db, metadata, why,
    ):
        """Re-review fix (2): present but unusable is REPORTED."""
        doc = _make_doc(db)
        box = OCRGeometryBox(
            text=why, bbox=[0.1, 0.1, 0.2, 0.05], level="line", metadata=metadata,
        )
        _make_regions_artifact(db, doc.id, boxes=[box])

        segment = _get(client, doc.id).json()["segments"][0]
        assert segment["anchor"].get("polygon") is None
        assert "geometry_problem" in segment["metadata"], why

    @pytest.mark.parametrize(
        "baseline_px, why",
        [
            pytest.param([[0, 90]], "one point", id="one-point"),
            pytest.param([[0, 90], [2000, 90]], "off the frame", id="off-frame"),
            pytest.param([[0, 90], [float("nan"), 90]], "NaN", id="nan"),
        ],
    )
    def test_unusable_baseline_is_reported_and_left_unset(self, client, db, baseline_px, why):
        """Re-review fix (3): the baseline is validated like a polygon's
        points; a bad one is reported, never passed through to fail the
        whole response one layer up in the typed Swift client."""
        doc = _make_doc(db)
        box = OCRGeometryBox(
            text=why, bbox=[0.1, 0.1, 0.2, 0.05], level="line",
            metadata={"baseline_px": baseline_px, "pixel_frame": {"width": 1000, "height": 1000}},
        )
        _make_regions_artifact(db, doc.id, boxes=[box])

        segment = _get(client, doc.id).json()["segments"][0]
        assert segment["baseline"] is None, why
        assert "geometry_problem" in segment["metadata"], why

    def test_response_json_never_carries_a_null_inside_a_numeric_list(self, client, db):
        """Re-review fix (3), pinned at the real failure point: a NaN
        serialised as `null` inside `list[list[float]]` would fail the
        WHOLE typed Swift response, not just this one segment."""
        doc = _make_doc(db)
        boxes = [
            OCRGeometryBox(
                text="bad baseline", bbox=[0.1, 0.1, 0.2, 0.05], level="line",
                metadata={
                    "baseline_px": [[0, 90], [float("nan"), 90]],
                    "polygon_px": [[0, 0], [500, 0], [500, 100], [0, 100]],
                    "pixel_frame": {"width": 1000, "height": 1000},
                },
            ),
            OCRGeometryBox(
                text="good", bbox=[0.3, 0.3, 0.1, 0.1], level="word",
                metadata={
                    "polygon_px": [[0, 0], [100, 0], [100, 100], [0, 100]],
                    "baseline_px": [[0, 90], [100, 90]],
                    "pixel_frame": {"width": 1000, "height": 1000},
                },
            ),
        ]
        _make_regions_artifact(db, doc.id, boxes=boxes)

        r = _get(client, doc.id)
        assert r.status_code == 200
        for segment in r.json()["segments"]:
            for numeric_list_name in ("baseline",):
                value = segment.get(numeric_list_name)
                if value is not None:
                    assert None not in [c for point in value for c in point]
            polygon = segment["anchor"].get("polygon")
            if polygon is not None:
                assert None not in [c for point in polygon for c in point]

    def test_char_end_before_char_start_drops_the_span_not_the_rect(self, client, db):
        """The follow-up: `char_end < char_start` used to drop the rect too
        (every attempt shared the span); the span is dropped first now, so
        a good rect survives."""
        doc = _make_doc(db)
        box = OCRGeometryBox(
            text="bad span", bbox=[0.1, 0.1, 0.2, 0.05], level="word",
            char_start=5, char_end=2,
        )
        _make_regions_artifact(db, doc.id, boxes=[box])

        segment = _get(client, doc.id).json()["segments"][0]
        assert segment["anchor"]["rect"] == [0.1, 0.1, 0.2, 0.05]
        assert segment["anchor"].get("char_start") is None
        assert segment["anchor"].get("char_end") is None
        assert "character span dropped" in segment["metadata"]["geometry_problem"]


class TestProvisionalIdsRefused:
    def test_assert_not_provisional_refuses_a_legacy_id(self):
        """source.seam.provisional-ids-refused."""
        from fichero_server.models.segments import (
            ProvisionalSegmentIdError,
            assert_not_provisional,
        )

        with pytest.raises(ProvisionalSegmentIdError):
            assert_not_provisional("legacy:abc123:0")
        assert_not_provisional("abc123")  # a real id passes silently

    def test_regions_edit_route_refuses_a_legacy_artifact_id(self, client, db):
        """The refusal is real, not decorative: the live write path calls it."""
        doc = _make_doc(db)
        artifact = _make_regions_artifact(db, doc.id)
        legacy_id = f"legacy:{artifact.id}"

        r = client.put(
            f"/api/artifacts/{legacy_id}/regions",
            json={"op": "move", "indices": [0], "bbox": [0.2, 0.2, 0.2, 0.05]},
        )
        assert r.status_code == 422
        assert "provisional" in r.json()["detail"]
        # Untouched — the refusal happened before any lookup or write.
        assert db.get(Artifact, artifact.id).ocr_geometry.boxes[0].bbox == [0.1, 0.1, 0.2, 0.05]


class TestOneMappingFunction:
    """A SOURCE SCAN, not a behaviour test — it proves the two modules
    mention the right function names, nothing about runtime behaviour. Keep
    it only as a companion to the real hard gate in
    test_mcp_server_contract.py::test_segments_hard_gate_same_ids_and_rects_everywhere
    (same ids/rects from the route, the MCP tool and the generated CLI
    command, against a live engine). If that test cannot be made to run,
    this one does NOT stand in for it."""

    def test_route_and_cli_client_both_resolve_through_segments_from_result(self):
        import inspect

        from fichero_cli.client import FicheroClient
        from fichero_server.api.routes.document import segments as segments_route

        route_source = inspect.getsource(segments_route)
        assert "segments_from_result(" in route_source
        # The CLI client validates the SAME response shape the route
        # returns — it does not re-derive segments from ocr_geometry itself.
        client_source = inspect.getsource(FicheroClient.list_segments)
        assert "segments_from_result" not in client_source
        assert "SegmentListResponse.model_validate" in client_source


class TestQueryFilters:
    def test_artifact_id_pass_id_and_kind_filter(self, client, db):
        doc = _make_doc(db)
        a1 = _make_regions_artifact(db, doc.id)
        a2 = _make_regions_artifact(db, doc.id, boxes=[
            OCRGeometryBox(text="delta", bbox=[0.5, 0.5, 0.1, 0.1], level="word"),
        ])

        by_artifact = _get(client, doc.id, artifact_id=a1.id).json()
        assert {s["source_artifact_id"] for s in by_artifact["segments"]} == {a1.id}

        by_pass = _get(client, doc.id, pass_id=f"legacy:{a2.id}").json()
        assert {s["text"] for s in by_pass["segments"]} == {"delta"}

        by_kind = _get(client, doc.id, kind="word").json()
        assert all(s["kind"] == "word" for s in by_kind["segments"])


class TestOrder:
    def test_passes_sorted_by_created_at_then_id_segments_in_box_order(self, client, db):
        """Order is stated, not 'whatever the store returns' -- or the
        route/MCP/CLI parity test would be flaky and the app's index
        mapping fragile."""
        doc = _make_doc(db)
        # Two boxes on the SAME artifact: box order must survive.
        first = OCRGeometryBox(text="first", bbox=[0.1, 0.1, 0.1, 0.1], level="word")
        second = OCRGeometryBox(text="second", bbox=[0.3, 0.3, 0.1, 0.1], level="word")
        newer = _make_regions_artifact(db, doc.id, boxes=[first, second])
        newer.created_at = newer.created_at.replace(year=newer.created_at.year + 1)
        db.save(newer)

        older = _make_regions_artifact(db, doc.id, boxes=[
            OCRGeometryBox(text="older", bbox=[0.5, 0.5, 0.1, 0.1], level="word"),
        ])
        older.created_at = older.created_at.replace(year=older.created_at.year - 1)
        db.save(older)

        body = _get(client, doc.id).json()
        assert [p["id"] for p in body["passes"]] == [
            f"legacy:{older.id}", f"legacy:{newer.id}",
        ]
        newer_segments = [s for s in body["segments"] if s["source_artifact_id"] == newer.id]
        assert [s["text"] for s in newer_segments] == ["first", "second"]


class TestDeniedViewer:
    def test_viewer_denied_the_document_is_refused(self, multiuser_client, app_db, users, db):
        """'Who may read': a viewer denied a document is refused (spec:
        slice 1, 'Tests include a viewer who is denied the document being
        refused')."""
        client, login, library_path = multiuser_client
        _grant(app_db, users.owner, library_path, "owner")
        _grant(app_db, users.viewer, library_path, "viewer")

        doc = _make_doc(db, name="denied-segments.jpg")
        _make_regions_artifact(db, doc.id)
        app_db.set_library_acl_override(
            user_id=users.viewer.id,
            library_path=authz.normalize_library_path(library_path),
            target_id=doc.id,
            effect="deny",
        )

        response = client.get(
            f"/api/segments/document/{doc.id}", headers=login("viewer"),
        )
        assert response.status_code == 403


class TestHandDrawnAndPassProvenanceSingleSignals:
    """test-audit F5/F6, 2026-09-20: every existing fixture sets BOTH
    `provider="user"` and `source="manual"` together, so no test proves
    `_box_is_hand_drawn`'s OR is real (either signal alone would pass even
    if the function were wrongly an AND), and no test proves
    `_derive_pass_provenance_kind`'s "model alone means workflow" branch
    or that both functions lower-case before comparing."""

    def test_provider_user_alone_is_hand_drawn(self):
        from fichero_server.media.ocr_geometry import OCRGeometryBox
        from fichero_server.models.segments import _box_is_hand_drawn

        box = OCRGeometryBox(text="x", bbox=[0.1, 0.1, 0.1, 0.1], level="word", provider="user")
        assert _box_is_hand_drawn(box) is True

    def test_source_manual_alone_is_hand_drawn(self):
        from fichero_server.media.ocr_geometry import OCRGeometryBox
        from fichero_server.models.segments import _box_is_hand_drawn

        box = OCRGeometryBox(text="x", bbox=[0.1, 0.1, 0.1, 0.1], level="word", source="manual")
        assert _box_is_hand_drawn(box) is True

    def test_neither_signal_is_not_hand_drawn(self):
        from fichero_server.media.ocr_geometry import OCRGeometryBox
        from fichero_server.models.segments import _box_is_hand_drawn

        box = OCRGeometryBox(text="x", bbox=[0.1, 0.1, 0.1, 0.1], level="word", provider="apple_vision")
        assert _box_is_hand_drawn(box) is False

    def test_signals_are_case_insensitive(self):
        from fichero_server.media.ocr_geometry import OCRGeometryBox
        from fichero_server.models.segments import _box_is_hand_drawn

        assert _box_is_hand_drawn(
            OCRGeometryBox(text="x", bbox=[0.1, 0.1, 0.1, 0.1], level="word", provider="USER")
        ) is True
        assert _box_is_hand_drawn(
            OCRGeometryBox(text="x", bbox=[0.1, 0.1, 0.1, 0.1], level="word", source="MANUAL")
        ) is True

    def test_model_alone_with_no_provider_means_workflow(self):
        from fichero_server.models.segments import _derive_pass_provenance_kind

        assert _derive_pass_provenance_kind(provider=None, model="apple-vision-v3") == "workflow"

    def test_provider_user_means_human_even_with_a_model_set(self):
        from fichero_server.models.segments import _derive_pass_provenance_kind

        assert _derive_pass_provenance_kind(provider="user", model="some-model") == "human"

    def test_neither_provider_nor_model_is_unknown_not_a_trusting_default(self):
        from fichero_server.models.segments import _derive_pass_provenance_kind

        assert _derive_pass_provenance_kind(provider=None, model=None) == "unknown"


class TestSegmentProvenanceKind:
    """`source.seam.maker-for-each-segment` (#4919): `SegmentRead.provenance_kind`
    is the box-level signal the app's ranking needs
    (agent-work/source-model/recon-app-slice-A.md, headline a) that the pass
    alone cannot give it -- a hand-added box inside an otherwise machine
    artifact."""

    def test_machine_artifact_with_one_hand_added_box(self, client, db):
        """source.seam.maker-for-each-segment."""
        doc = _make_doc(db)
        boxes = [
            OCRGeometryBox(text="machine one", bbox=[0.1, 0.1, 0.1, 0.1], level="word", provider="apple_vision"),
            OCRGeometryBox(text="hand added", bbox=[0.3, 0.3, 0.1, 0.1], level="word", provider="user", source="manual"),
            OCRGeometryBox(text="machine two", bbox=[0.5, 0.5, 0.1, 0.1], level="word", provider="apple_vision"),
        ]
        _make_regions_artifact(db, doc.id, boxes=boxes, provider="apple_vision")

        segments = _get(client, doc.id).json()["segments"]
        by_text = {s["text"]: s["provenance_kind"] for s in segments}
        assert by_text == {
            "machine one": "workflow",
            "hand added": "human",
            "machine two": "workflow",
        }

    def test_artifact_with_provider_user_is_human_throughout(self, client, db):
        """source.seam.maker-for-each-segment."""
        doc = _make_doc(db)
        boxes = [
            OCRGeometryBox(text="a", bbox=[0.1, 0.1, 0.1, 0.1], level="word"),
            OCRGeometryBox(text="b", bbox=[0.3, 0.3, 0.1, 0.1], level="word"),
        ]
        _make_regions_artifact(db, doc.id, boxes=boxes, provider="user")

        segments = _get(client, doc.id).json()["segments"]
        assert all(s["provenance_kind"] == "human" for s in segments)

    def test_box_with_neither_signal_takes_the_passs_kind(self, client, db):
        """source.seam.maker-for-each-segment."""
        doc = _make_doc(db)
        box = OCRGeometryBox(text="plain", bbox=[0.1, 0.1, 0.1, 0.1], level="word")
        _make_regions_artifact(db, doc.id, boxes=[box], provider=None, model=None)

        segments = _get(client, doc.id).json()["segments"]
        assert segments[0]["provenance_kind"] == "unknown"
        assert _get(client, doc.id).json()["passes"][0]["provenance_kind"] == "unknown"

    def test_hand_added_box_through_the_real_regions_edit_route(self, client, db):
        """source.seam.maker-for-each-segment. Follow-up (10): provider
        'user' is PROVEN through the live write path
        (`artifact.regions_edit`'s ADD op), not assumed by a fixture that
        hand-sets it."""
        doc = _make_doc(db)
        artifact = _make_regions_artifact(
            db, doc.id,
            boxes=[OCRGeometryBox(text="machine", bbox=[0.1, 0.1, 0.1, 0.1], level="word")],
            provider="apple_vision",
        )

        r = client.put(
            f"/api/artifacts/{artifact.id}/regions",
            json={"op": "add", "bbox": [0.6, 0.6, 0.1, 0.1], "text": "curated", "level": "word"},
        )
        assert r.status_code == 200

        segments = _get(client, doc.id).json()["segments"]
        by_text = {s["text"]: s["provenance_kind"] for s in segments}
        assert by_text == {"machine": "workflow", "curated": "human"}


class TestSlice1bAdditions:
    """SegmentRead.page_index, PassRead.text, PassRead.provider (#4919,
    slice 1b -- build-notes-identity-and-storage.md)."""

    def test_each_segment_carries_its_page_index_and_filtering_isolates_pages(
        self, client, db,
    ):
        """A two-page PDF fixture: every segment carries its page's index,
        and filtering by it (client-side -- there is no page query param in
        this slice) gives each page only its own boxes."""
        doc = _make_doc(db)
        boxes = [
            OCRGeometryBox(text="p0 word", bbox=[0.1, 0.1, 0.1, 0.1], level="word", page_index=0),
            OCRGeometryBox(text="p0 word2", bbox=[0.2, 0.2, 0.1, 0.1], level="word", page_index=0),
            OCRGeometryBox(text="p1 word", bbox=[0.1, 0.1, 0.1, 0.1], level="word", page_index=1),
        ]
        _make_regions_artifact(db, doc.id, boxes=boxes)

        segments = _get(client, doc.id).json()["segments"]
        assert [s["page_index"] for s in segments] == [0, 0, 1]

        page_0 = [s for s in segments if s["page_index"] == 0]
        page_1 = [s for s in segments if s["page_index"] == 1]
        assert {s["text"] for s in page_0} == {"p0 word", "p0 word2"}
        assert {s["text"] for s in page_1} == {"p1 word"}

    def test_pass_text_indexes_correctly_and_is_never_a_join_of_box_texts(
        self, client, db,
    ):
        """PassRead.text is the result's OWN text; a box's char_start/char_end
        index into THAT text. A naive join of box texts with spaces would
        NOT equal it here (the source has irregular spacing), so the test
        fails if anything rebuilds pass.text from the boxes."""
        result_text = "Alpha,  Beta -- Gamma"  # NOT "Alpha Beta Gamma"
        naive_join = " ".join(["Alpha", "Beta", "Gamma"])
        assert result_text != naive_join

        boxes = [
            OCRGeometryBox(text="Alpha", bbox=[0.1, 0.1, 0.1, 0.1], level="word",
                            char_start=0, char_end=5),
            OCRGeometryBox(text="Beta", bbox=[0.2, 0.2, 0.1, 0.1], level="word",
                            char_start=8, char_end=12),
            OCRGeometryBox(text="Gamma", bbox=[0.3, 0.3, 0.1, 0.1], level="word",
                            char_start=16, char_end=21),
        ]
        doc = _make_doc(db)
        _make_regions_artifact(db, doc.id, boxes=boxes)
        # Override the fixture's own text with our irregularly-spaced one.
        stored = db.query(Artifact, document_id=doc.id)[0]
        stored.ocr_geometry = stored.ocr_geometry.model_copy(update={"text": result_text})
        db.save(stored)

        body = _get(client, doc.id).json()
        pass_text = body["passes"][0]["text"]
        assert pass_text == result_text
        assert pass_text != naive_join

        for segment in body["segments"]:
            char_start = segment["anchor"]["char_start"]
            char_end = segment["anchor"]["char_end"]
            assert pass_text[char_start:char_end] == segment["text"]

    def test_pass_provider_is_the_artifacts_provider_not_its_type(self, client, db):
        """PassRead.provider is the ARTIFACT's provider; `name` stays a
        display name (the artifact's type)."""
        doc = _make_doc(db)
        _make_regions_artifact(db, doc.id, provider="apple_vision")

        pass_read = _get(client, doc.id).json()["passes"][0]
        assert pass_read["provider"] == "apple_vision"
        assert pass_read["name"] == "regions"  # the artifact_type, a display name
        assert pass_read["name"] != pass_read["provider"]
