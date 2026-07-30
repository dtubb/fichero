"""Preset-version bump guardrail (#4298).

``seed_default_workflows`` only force-replaces a stored preset copy when the
shipped ``config.preset_version`` is GREATER than the stored one. The
paleography-ensemble widening bug shipped because the preset's graph was fixed
four times while ``preset_version`` stayed at 1 — every already-seeded library
kept the broken stored graph forever. These tests pin the discipline: editing
a shipped preset without bumping its version fails the suite.

Each violation class has a fixture proving the rule FIRES
(guardrails-must-match-granularity).
"""

from __future__ import annotations

import json

from fichero_server.workflows.preset_manifest import (
    MANIFEST_PATH,
    build_manifest,
    check_preset_manifest,
    load_manifest,
    load_shipped_presets,
)


def _preset_bytes(version: int, extra: str = "") -> bytes:
    return json.dumps({"config": {"preset_version": version}, "nodes": [extra]}).encode()


class TestGuardrailFires:
    def test_content_change_without_bump_fires(self):
        old = _preset_bytes(1)
        manifest = build_manifest({"p.json": (old, 1)})
        violations = check_preset_manifest({"p.json": (_preset_bytes(1, "edited"), 1)}, manifest)
        assert len(violations) == 1
        assert "content changed but preset_version is still 1" in violations[0]

    def test_content_change_with_bump_requires_manifest_refresh(self):
        manifest = build_manifest({"p.json": (_preset_bytes(1), 1)})
        violations = check_preset_manifest({"p.json": (_preset_bytes(2, "edited"), 2)}, manifest)
        assert len(violations) == 1
        assert "refresh the manifest" in violations[0]

    def test_unrecorded_preset_fires(self):
        violations = check_preset_manifest({"new.json": (_preset_bytes(1), 1)}, {})
        assert len(violations) == 1
        assert "not in preset_version_manifest.json" in violations[0]

    def test_removed_preset_fires(self):
        manifest = build_manifest({"gone.json": (_preset_bytes(1), 1)})
        violations = check_preset_manifest({}, manifest)
        assert len(violations) == 1
        assert "not shipped" in violations[0]

    def test_version_drift_on_unchanged_content_fires(self):
        raw = _preset_bytes(1)
        manifest = build_manifest({"p.json": (raw, 1)})
        violations = check_preset_manifest({"p.json": (raw, 3)}, manifest)
        assert len(violations) == 1
        assert "disagrees with manifest" in violations[0]

    def test_clean_state_passes(self):
        presets = {"p.json": (_preset_bytes(2), 2)}
        assert check_preset_manifest(presets, build_manifest(presets)) == []


class TestShippedPresets:
    def test_manifest_exists(self):
        assert MANIFEST_PATH.exists(), (
            "preset_version_manifest.json is missing — regenerate with "
            "python -m fichero_server.workflows.preset_manifest --regen"
        )

    def test_every_shipped_preset_matches_the_manifest(self):
        violations = check_preset_manifest(load_shipped_presets(), load_manifest())
        assert violations == [], "\n".join(violations)

    def test_ensemble_preset_was_bumped_past_the_stale_stored_copies(self):
        """The #4298 repro class: libraries seeded before #4146 hold an
        ensemble graph whose zoom node has no documents wiring at
        preset_version 1. The shipped preset must stay ABOVE 1 so seeding
        force-replaces those stored copies."""
        presets = load_shipped_presets()
        _, version = presets["transcribe_paleography_ensemble.json"]
        assert version >= 2
