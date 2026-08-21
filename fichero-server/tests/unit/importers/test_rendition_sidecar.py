"""Reading the staging pipeline's .renditions.json contract.

Fixtures below are trimmed from the real Marshall corpus (151 sidecars in
NCM_Diary_19330101-19331231: 148 split halves, 3 whole pages), so the shapes
tested are the shapes that actually exist rather than ones I invented.
"""

from __future__ import annotations

import json

from fichero_server.importers.rendition_sidecar import (
    load_sidecar,
    plan_renditions,
    sidecar_path_for,
)
from fichero_server.models.anchors import RegionConfidence

SPLIT_PART = {
    "schema": "fichero-page-renditions-v0-proposed",
    "page_external_id": "diary__IMG_067_part_1",
    "original_image_stem": "IMG_067",
    "part": 1,
    "region_on_original": {
        "bbox": [0.0, 0.0, 0.5, 1.0],
        "space": "page-relative-fraction",
        "method": "nominal-even-split",
        "confidence": "nominal",
        "note": "the fold was not measured",
    },
    "renditions": [
        {"role": "enhanced", "path": "/p/IMG_067_part_1.jpg", "primary": True},
        {"role": "background_removed", "path": "/p/_r/IMG_067_part_1.bg.png", "primary": False},
        {
            "role": "original",
            "path": "/p/_r/IMG_067.original.jpg",
            "primary": False,
            "storage": "staged",
            "materialized": True,
        },
    ],
}

WHOLE_PAGE = {
    "schema": "fichero-page-renditions-v0-proposed",
    "page_external_id": "diary__IMG_002",
    "original_image_stem": "IMG_002",
    "part": None,
    "region_on_original": {
        "bbox": [0.0, 0.0, 1.0, 1.0],
        "space": "page-relative-fraction",
        "method": "whole-page",
        "confidence": "exact",
    },
    "renditions": [
        {"role": "enhanced", "path": "/p/IMG_002.jpg", "primary": True},
        {"role": "original", "path": "/p/_r/IMG_002.original.jpg", "primary": False},
    ],
}


class TestSplitPart:
    def test_same_frame_renditions_attach(self):
        plan = plan_renditions("doc-1", SPLIT_PART)
        assert [r.role for r in plan.renditions] == ["enhanced", "background_removed"]
        assert plan.renditions[0].is_primary is True

    def test_original_of_a_part_is_deferred_not_attached(self):
        """The whole opening is a DIFFERENT frame. Attaching it to the part
        would reproduce the exact mis-registration this model prevents."""
        plan = plan_renditions("doc-1", SPLIT_PART)
        assert [role for role, _, _ in plan.deferred] == ["original"]
        assert "different" in plan.deferred[0][2]
        assert all(r.role != "original" for r in plan.renditions)

    def test_region_in_parent_is_carried_with_its_honesty(self):
        plan = plan_renditions("doc-1", SPLIT_PART)
        assert plan.region_in_parent is not None
        assert plan.region_in_parent.rect == [0.0, 0.0, 0.5, 1.0]
        assert plan.region_in_parent.method == "nominal-even-split"
        assert plan.region_in_parent.confidence is RegionConfidence.nominal


class TestWholePage:
    def test_original_attaches_because_it_is_the_same_frame(self):
        """part is null, so `original` really is this page's own original."""
        plan = plan_renditions("doc-2", WHOLE_PAGE)
        assert sorted(r.role for r in plan.renditions) == ["enhanced", "original"]
        assert plan.deferred == []

    def test_no_region_in_parent_for_a_whole_page(self):
        """[0,0,1,1] is a region on ITSELF; recording it as a region in a
        parent would assert a containment that does not exist."""
        assert plan_renditions("doc-2", WHOLE_PAGE).region_in_parent is None

    def test_exact_confidence_maps_to_measured_losing_nothing(self):
        """`exact` is not a fourth enum value — the distinction it carries is
        already preserved verbatim in method ("whole-page")."""
        part_like = {**WHOLE_PAGE, "part": 2}
        plan = plan_renditions("doc-2", part_like)
        assert plan.region_in_parent.confidence is RegionConfidence.measured
        assert plan.region_in_parent.method == "whole-page"


class TestDegradation:
    def test_unknown_schema_is_skipped_with_a_warning(self):
        plan = plan_renditions("doc-1", {"schema": "something-else", "renditions": []})
        assert plan.renditions == []
        assert any("unsupported sidecar schema" in w for w in plan.warnings)

    def test_unknown_confidence_downgrades_to_weakest_and_says_so(self):
        """Never upgrade an unrecognised vocabulary. Downgrading silently
        would still be a lie; downgrading loudly is honest."""
        odd = json.loads(json.dumps(SPLIT_PART))
        odd["region_on_original"]["confidence"] = "pretty-sure"
        plan = plan_renditions("doc-1", odd)
        assert plan.region_in_parent.confidence is RegionConfidence.nominal
        assert any("pretty-sure" in w for w in plan.warnings)
        assert "pretty-sure" in plan.region_in_parent.note

    def test_unsupported_space_drops_the_region_rather_than_guessing(self):
        odd = json.loads(json.dumps(SPLIT_PART))
        odd["region_on_original"]["space"] = "pixels"
        plan = plan_renditions("doc-1", odd)
        assert plan.region_in_parent is None
        assert any("unsupported region space" in w for w in plan.warnings)
        # The renditions themselves are unaffected by a bad region.
        assert len(plan.renditions) == 2

    def test_entry_missing_role_or_path_is_warned_not_crashed(self):
        odd = json.loads(json.dumps(SPLIT_PART))
        odd["renditions"].append({"role": "thumbnail"})
        plan = plan_renditions("doc-1", odd)
        assert any("missing role/path" in w for w in plan.warnings)
        assert all(r.role != "thumbnail" for r in plan.renditions)

    def test_malformed_bbox_drops_the_region_only(self):
        odd = json.loads(json.dumps(SPLIT_PART))
        odd["region_on_original"]["bbox"] = [0.0, 0.0]
        plan = plan_renditions("doc-1", odd)
        assert plan.region_in_parent is None
        assert len(plan.renditions) == 2


class TestLoading:
    def test_sidecar_path_appends_to_the_full_filename(self, tmp_path):
        """Not a suffix swap — the sidecar sits beside IMG_067.jpg as
        IMG_067.jpg.renditions.json."""
        assert sidecar_path_for(tmp_path / "IMG_067.jpg").name == (
            "IMG_067.jpg.renditions.json"
        )

    def test_missing_sidecar_is_none_not_an_error(self, tmp_path):
        assert load_sidecar(tmp_path / "nothing.jpg") is None

    def test_unreadable_sidecar_warns_and_returns_none(self, tmp_path):
        """One bad sidecar must not fail a 450-page import whose documents
        already committed."""
        source = tmp_path / "IMG_001.jpg"
        sidecar_path_for(source).write_text("{ not json", encoding="utf-8")
        assert load_sidecar(source) is None

    def test_round_trip_from_disk(self, tmp_path):
        source = tmp_path / "IMG_067_part_1.jpg"
        sidecar_path_for(source).write_text(json.dumps(SPLIT_PART), encoding="utf-8")
        loaded = load_sidecar(source)
        assert loaded is not None
        plan = plan_renditions("doc-1", loaded)
        assert len(plan.renditions) == 2
        assert plan.region_in_parent.rect == [0.0, 0.0, 0.5, 1.0]
