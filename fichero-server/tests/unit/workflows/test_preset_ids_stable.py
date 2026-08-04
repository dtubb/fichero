"""Shipped preset ids must be stable across seeds and upgrades (#4450).

`seed_default_workflows` built `Workflow(...)` with no id, so every seed
minted a fresh random UUID — and the auto-upgrade path DELETES+REINSERTS a
preset whenever `preset_version` bumps. After an upgrade the old id existed
in NO workflow table: the sidebar still offered it, the execute route's
library lookup missed, the global-defaults fallback missed too, and the user
saw "not found in this library" for a workflow the UI itself was offering.

Two guarantees pinned here:

* the same preset seeds the SAME deterministic id everywhere (uuid5 over a
  fixed fichero namespace + the preset's stable name), so the global library
  and every user library agree about what "Transcribe" is;
* a preset_version bump (and force-reinstall) reinserts WITH the id the
  replaced row held — an update-in-place as far as any reference holder can
  tell, so upgrades never orphan cached ids, run rows, or sidebar entries.
  Libraries holding pre-#4450 random ids keep them: mapping is by name.

Nothing here skips or calls a model.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from fichero_server.models import Workflow
from fichero_server.workflows.default_workflows import (
    _load_preset_files,
    preset_workflow_id,
    seed_default_workflows,
)


def _empty_db() -> MagicMock:
    db = MagicMock()
    db.all.return_value = []
    db.save = MagicMock()
    db.delete = MagicMock()
    return db


class TestDeterministicPresetIds:
    def test_same_name_always_mints_the_same_id(self):
        assert preset_workflow_id("Transcribe") == preset_workflow_id("Transcribe")

    def test_different_names_mint_different_ids(self):
        assert preset_workflow_id("Transcribe") != preset_workflow_id("Catalogue")

    def test_the_id_is_a_valid_uuid(self):
        uuid.UUID(preset_workflow_id("Transcribe"))  # raises if not

    def test_fresh_seed_uses_the_deterministic_id_for_every_preset(self):
        db = _empty_db()
        seeded = seed_default_workflows(db)
        assert seeded > 0
        for call in db.save.call_args_list:
            wf = call.args[0]
            assert wf.id == preset_workflow_id(wf.name), (
                f"preset {wf.name!r} seeded with a random id — a re-seed "
                "elsewhere would mint a different one and cross-library "
                "references break again (#4450)"
            )

    def test_two_libraries_seed_identical_ids(self):
        """The #4450 resolution contract: the sidebar can hold the global
        library's id for a preset and a fresh user library agrees on it."""
        db_a, db_b = _empty_db(), _empty_db()
        seed_default_workflows(db_a)
        seed_default_workflows(db_b)
        ids_a = {c.args[0].name: c.args[0].id for c in db_a.save.call_args_list}
        ids_b = {c.args[0].name: c.args[0].id for c in db_b.save.call_args_list}
        assert ids_a == ids_b


def _stored_preset(name: str, preset_version: int) -> Workflow:
    """An already-seeded template row holding a pre-#4450 random id."""
    wf = Workflow(
        name=name,
        is_template=True,
        is_system=True,
        config={"preset_version": preset_version},
    )
    assert wf.id != preset_workflow_id(name)  # random, as before the fix
    return wf


def _shipped_preset_name() -> str:
    """A preset name guaranteed to be in the shipped JSON set."""
    names = {p["name"] for p in _load_preset_files()}
    assert "Transcribe" in names
    return "Transcribe"


class TestUpgradesNeverOrphanReferences:
    def test_a_version_bump_reinserts_with_the_same_id(self):
        """The reported mechanism: preset_version bumps → delete+reinsert →
        the old id exists nowhere → every holder of it 404s. The upgrade must
        keep the id the replaced row held."""
        name = _shipped_preset_name()
        stored = _stored_preset(name, preset_version=0)  # shipped is >= 1
        old_id = stored.id

        db = _empty_db()
        db.all.return_value = [stored]
        seed_default_workflows(db)

        deleted = [c.args[0] for c in db.delete.call_args_list]
        assert stored in deleted, "precondition: the version bump upgraded it"
        reinserted = {c.args[0].name: c.args[0] for c in db.save.call_args_list}
        assert name in reinserted, "the upgraded preset was not reinserted"
        assert reinserted[name].id == old_id, (
            "the upgrade minted a new id — every reference to the old one "
            "(sidebar entries, cached defaults, run rows) is orphaned (#4450)"
        )

    def test_force_reinstall_also_preserves_ids(self):
        name = _shipped_preset_name()
        stored = _stored_preset(name, preset_version=999_999)  # no bump needed
        old_id = stored.id

        db = _empty_db()
        db.all.return_value = [stored]
        seed_default_workflows(db, force=True)

        reinserted = {c.args[0].name: c.args[0] for c in db.save.call_args_list}
        assert name in reinserted
        assert reinserted[name].id == old_id

    def test_an_unbumped_preset_is_left_entirely_alone(self):
        """Stability the other way: no bump, no force — the stored row (and
        its id) must not be touched at all."""
        name = _shipped_preset_name()
        stored = _stored_preset(name, preset_version=999_999)

        db = _empty_db()
        db.all.return_value = [stored]
        seed_default_workflows(db)

        deleted_names = [c.args[0].name for c in db.delete.call_args_list]
        saved_names = [c.args[0].name for c in db.save.call_args_list]
        assert name not in deleted_names
        assert name not in saved_names
