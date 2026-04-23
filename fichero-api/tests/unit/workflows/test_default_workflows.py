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
        presets = {p["name"]: p for p in _load_preset_files()}
        catalogue = presets["Catalogue"]

        node_tools = {n["id"]: n["tool"] for n in catalogue["nodes"]}
        # Expected shape: source → per-file tool → reduce.
        assert "files" in node_tools.values()
        assert "transcribe" in node_tools.values()
        assert "catalogue" in node_tools.values()

        # Edge connects transcribe.text → catalogue.text so the aggregated
        # transcription reaches the catalogue step.
        edges = catalogue["edges"]
        cat_edge = next(
            e for e in edges if e["target_node_id"] == _node_id(catalogue, "catalogue")
        )
        assert cat_edge["source_port_id"] == "text"
        assert cat_edge["target_port_id"] == "text"


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
        db = self._mock_db(existing_names=["Transcribe"])
        seeded = seed_default_workflows(db)
        # Catalogue still seeds but Transcribe does not.
        saved_names = [call.args[0].name for call in db.save.call_args_list]
        assert "Transcribe" not in saved_names
        assert "Catalogue" in saved_names
        assert seeded == len(saved_names)

    def test_idempotent_second_run_seeds_nothing(self):
        db = self._mock_db(existing_names=["Transcribe", "Catalogue"])
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
