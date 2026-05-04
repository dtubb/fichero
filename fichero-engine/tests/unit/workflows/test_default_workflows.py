"""
Tests for default workflow preset loading and seeding.

Seeding must be idempotent: running it twice on the same library inserts
presets once only. Presets must be loadable from the packaged resources
directory without hitting disk outside of the known presets location.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fichero.workflows.default_workflows import (
    _load_preset_files,
    seed_default_workflows,
)


class TestLoadPresetFiles:
    def test_discovers_shipped_presets(self):
        presets = _load_preset_files()
        # We ship at least Transcribe and Catalogue as 0.0.2 defaults.
        names = {p.get("name") for p in presets}
        assert "Transcribe" in names
        assert "Catalogue" in names

    def test_every_preset_has_minimal_required_fields(self):
        for preset in _load_preset_files():
            assert preset.get("name"), f"preset missing name: {preset}"
            # Nodes-format presets must have at least one node.
            if preset.get("format") == "nodes":
                assert preset.get("nodes"), f"{preset['name']} has no nodes"

    def test_catalogue_preset_wiring(self):
        """The single 0.0.2 Catalogue preset is the full composable pipeline:
        Files → Transcribe → Aggregate → 6 extractors → merge → Catalogue.
        (The earlier 'Catalogue (composable)' variant was merged into the
        sole 'Catalogue' preset — runtime model picker replaces variants.)"""
        presets = {p["name"]: p for p in _load_preset_files()}
        catalogue = presets["Catalogue"]

        node_tools = {n["tool"] for n in catalogue["nodes"]}
        for tool in ("files", "transcribe", "aggregate", "catalogue"):
            assert tool in node_tools, f"preset missing {tool!r} node"

        # Edges use UI schema (source/target, source_port/target_port) so they
        # render in the workflow editor canvas.
        for edge in catalogue["edges"]:
            for key in ("source", "target", "source_port", "target_port"):
                assert key in edge, f"edge missing {key!r}: {edge}"

        # Transcribe → aggregate (per-page records flow downstream).
        transcribe_id = _node_id(catalogue, "transcribe")
        aggregate_ids = [n["id"] for n in catalogue["nodes"] if n["tool"] == "aggregate"]
        assert any(
            e["source"] == transcribe_id and e["target"] in aggregate_ids
            for e in catalogue["edges"]
        ), "transcribe must flow into aggregate"

    def test_catalogue_has_final_catalogue_node_fed_by_merge(self):
        """The preset must end with a catalogue node so the workflow produces
        a unified Catalogue artifact, not just per-entity outputs (#720)."""
        presets = {p["name"]: p for p in _load_preset_files()}
        catalogue = presets["Catalogue"]

        node_tools = {n["tool"] for n in catalogue["nodes"]}
        assert "catalogue" in node_tools

        # A merge/aggregate barrier feeds the final catalogue via text/text.
        catalogue_id = _node_id(catalogue, "catalogue")
        feeders = [
            e for e in catalogue["edges"]
            if e["target"] == catalogue_id and e["target_port"] == "text"
        ]
        assert feeders, "no edge feeds catalogue.text"

    def test_default_templates_have_folder_path_groups(self):
        """Templates ship with `folder_path` values so the Run Workflow
        context menu can render them in submenus (#722)."""
        presets = {p["name"]: p for p in _load_preset_files()}
        expected = {
            "Transcribe": "/Transcribe",
            "Catalogue": "/Catalogue",
        }
        for name, expected_path in expected.items():
            assert name in presets, f"missing preset: {name}"
            assert presets[name].get("folder_path") == expected_path

    def test_catalogue_uses_generic_extractors(self):
        """The Catalogue preset uses six generic per-entity extractors
        that produce individual artifacts in parallel. Archive-specific
        extractors stay registered as tools but are dropped from the default
        workflow per #726."""
        presets = {p["name"]: p for p in _load_preset_files()}
        node_tools = {n["tool"] for n in presets["Catalogue"]["nodes"]}
        for extractor in (
            "people_extract",
            "places_extract",
            "organizations_extract",
            "dates_extract",
            "events_extract",
            "keywords_extract",
        ):
            assert extractor in node_tools, (
                f"Catalogue preset missing generic extractor {extractor!r}"
            )

    def test_catalogue_drops_archive_specific_extractors(self):
        """Archive-specific extractors don't ship in the default workflow."""
        presets = {p["name"]: p for p in _load_preset_files()}
        node_tools = {n["tool"] for n in presets["Catalogue"]["nodes"]}
        archive_specific = {
            "rivers_extract", "mines_extract",
            "properties_extract", "legal_references_extract",
        }
        assert not (archive_specific & node_tools)


def _node_id(preset: dict, tool: str) -> str:
    for node in preset["nodes"]:
        if node["tool"] == tool:
            return node["id"]
    raise AssertionError(f"no node with tool {tool!r} in preset {preset['name']!r}")


class TestSeedDefaultWorkflows:
    def _mock_db(self, existing_names: list[str]):
        """Build a fake Database with a populated .all(Workflow) and saveable .save()."""
        from fichero.models import Workflow

        db = MagicMock()
        existing = [Workflow(name=name) for name in existing_names]
        db.all.return_value = existing
        db.save = MagicMock()
        return db

    def test_seeds_all_when_library_is_empty(self):
        db = self._mock_db(existing_names=[])
        seeded = seed_default_workflows(db)
        assert seeded >= 2  # Transcribe + Catalogue at minimum
        # Every save call should have been with a Workflow instance.
        assert db.save.call_count == seeded

    def test_skips_preset_that_already_exists(self):
        db = self._mock_db(existing_names=["Transcribe", "Transcribe (Apple Vision)"])
        seeded = seed_default_workflows(db)
        # Catalogue still seeds but Transcribe variants do not.
        saved_names = [call.args[0].name for call in db.save.call_args_list]
        assert "Transcribe" not in saved_names
        assert "Transcribe (Apple Vision)" not in saved_names
        assert "Catalogue" in saved_names
        assert seeded == len(saved_names)

    def test_idempotent_second_run_seeds_nothing(self):
        # Mark every shipped preset as already-seeded so no insert happens
        # on re-run. As new presets are added to resources/default_workflows,
        # include them here so the idempotency check stays accurate.
        db = self._mock_db(existing_names=[
            "Transcribe",
            "Transcribe (Apple Vision)",
            "Catalogue",
            "Catalogue (composable)",
            "Catalogue (Apple Intelligence)",
        ])
        seeded = seed_default_workflows(db)
        assert seeded == 0
        db.save.assert_not_called()

    def test_workflows_saved_are_templates_with_nodes_format(self):
        db = self._mock_db(existing_names=[])
        seed_default_workflows(db)
        for call in db.save.call_args_list:
            wf = call.args[0]
            assert wf.format == "nodes"
            assert wf.is_template is True
            assert wf.nodes, f"preset {wf.name} seeded with no nodes"

    def test_db_failure_during_list_returns_zero_without_raising(self):
        db = MagicMock()
        db.all.side_effect = RuntimeError("query failed")
        # Should not raise — seeding is best-effort and must not break library init.
        seeded = seed_default_workflows(db)
        assert seeded == 0

    def test_force_deletes_and_reseeds_template_workflows(self):
        """force=True must delete existing is_template=True presets by name
        and re-insert from JSON so shipping a new preset version reaches
        libraries that already have the old copy."""
        from fichero.models import Workflow

        db = MagicMock()
        old_catalogue = Workflow(name="Catalogue")
        old_catalogue.is_template = True
        old_transcribe = Workflow(name="Transcribe")
        old_transcribe.is_template = True
        db.all.return_value = [old_catalogue, old_transcribe]
        db.save = MagicMock()
        db.delete = MagicMock()

        seeded = seed_default_workflows(db, force=True)

        # Both old presets deleted.
        deleted_names = [call.args[0].name for call in db.delete.call_args_list]
        assert "Catalogue" in deleted_names
        assert "Transcribe" in deleted_names
        # Re-inserted from JSON.
        saved_names = [call.args[0].name for call in db.save.call_args_list]
        assert "Catalogue" in saved_names
        assert "Transcribe" in saved_names
        assert seeded == len(saved_names)

    def test_force_does_not_delete_user_duplicated_workflows(self):
        """A user-duplicated workflow with a preset name but is_template=False
        must NOT be deleted by force-reseed — that would destroy user work."""
        from fichero.models import Workflow

        db = MagicMock()
        user_copy = Workflow(name="Catalogue")
        user_copy.is_template = False  # user edited / duplicated
        db.all.return_value = [user_copy]
        db.save = MagicMock()
        db.delete = MagicMock()

        seed_default_workflows(db, force=True)

        db.delete.assert_not_called()
        # The preset also doesn't get re-seeded because the user's named
        # copy still exists — seeding would create a duplicate name.
        saved_names = [call.args[0].name for call in db.save.call_args_list]
        assert "Catalogue" not in saved_names
