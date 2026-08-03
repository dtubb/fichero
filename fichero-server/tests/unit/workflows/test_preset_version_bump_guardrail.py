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


# =============================================================================
# A version bump must never overwrite a preset the user has customised (#4501)
# =============================================================================


class TestAVersionBumpDoesNotEatUserWork:
    """Bumping `preset_version` force-replaces stored copies. That is the whole
    point — it is how a fix reaches an already-seeded library without the user
    clicking "Reinstall defaults" — but it is also, structurally, a re-run
    deleting rows. Today's other two defects were exactly that shape (#4415, a
    catalogue re-run hard-deleting corrected artifacts; #4499, a correction
    coming back as a duplicate), so the claim "this bump is safe" needs a test
    rather than a reading.

    It is safe because a customised preset is, by construction, no longer
    is_template/is_system, and the upgrade only touches rows that still are:

    - `is_system=True` presets are rejected read-only (403) — they cannot be
      edited in place at all, only duplicated.
    - `is_template=True` is DEMOTED to False the first time a user edits a
      preset (#780, "reinstall-defaults must NOT wipe it on next app launch").

    These tests pin that seam. If either guard is removed, a routine version
    bump silently starts eating user libraries.
    """

    def _preset_row(self, db, name, version, *, is_template, is_system):
        from fichero_server.models import Workflow

        wf = Workflow(
            id=f"wf-{name}",
            name=name,
            nodes=[],
            edges=[],
            config={"preset_version": version},
            is_template=is_template,
            is_system=is_system,
        )
        db.save(wf)
        return wf

    def test_a_customised_preset_is_not_replaced_by_a_bump(self, tmp_path):
        """The case that matters: the user edited it, so #780 demoted
        is_template, so the upgrade must leave it alone even though the shipped
        version is now higher."""
        from fichero_server.db import Database
        from fichero_server.models import Workflow
        from fichero_server.workflows.default_workflows import (
            _load_preset_files,
            seed_default_workflows,
        )

        shipped = _load_preset_files()[0]
        name = shipped["name"]

        db = Database(tmp_path / "user.fichero")
        # Customised: demoted by #780 on first edit, and carrying the user's
        # own marker so we can tell whether the row survived.
        self._preset_row(db, name, 1, is_template=False, is_system=False)
        row = db.get(Workflow, f"wf-{name}")
        row.description = "the user's own edit"
        db.save(row)

        seed_default_workflows(db)

        survivor = db.get(Workflow, f"wf-{name}")
        assert survivor is not None, (
            f"a version bump DELETED the user's customised {name!r}. A 'tested' "
            "flag must never become a mechanism that overwrites a library"
        )
        assert survivor.description == "the user's own edit"

    def test_an_untouched_shipped_copy_IS_upgraded_by_a_bump(self, tmp_path):
        """The other half. If nothing is replaced, the bump is pointless and
        `tested: true` would never reach an already-seeded library — the label
        would stay on presets that have been validated."""
        from fichero_server.db import Database
        from fichero_server.models import Workflow
        from fichero_server.workflows.default_workflows import (
            _load_preset_files,
            seed_default_workflows,
        )

        shipped = _load_preset_files()[0]
        name = shipped["name"]
        shipped_version = (shipped.get("config") or {}).get("preset_version", 1)

        db = Database(tmp_path / "stock.fichero")
        # Untouched shipped copy, one version behind.
        self._preset_row(
            db, name, shipped_version - 1, is_template=True, is_system=False
        )

        seed_default_workflows(db)

        rows = [w for w in db.all(Workflow) if w.name == name]
        assert rows, f"{name!r} vanished entirely instead of being upgraded"
        assert all(
            (w.config or {}).get("preset_version", 1) >= shipped_version
            for w in rows
        ), (
            "an untouched shipped preset was NOT upgraded, so a validated "
            "preset's config.tested never reaches existing libraries"
        )
