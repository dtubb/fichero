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
        for tool in ("files", "transcribe", "extract_all", "catalogue"):
            assert tool in node_tools, f"preset missing {tool!r} node"

        # Edges use UI schema (source/target, source_port/target_port) so they
        # render in the workflow editor canvas.
        for edge in catalogue["edges"]:
            for key in ("source", "target", "source_port", "target_port"):
                assert key in edge, f"edge missing {key!r}: {edge}"

        # Transcribe → extract_all (per-page text flows downstream via the
        # auto-aggregator; the user-aggregate Marshal node was removed
        # in the #837 fix because it created a super-step race).
        transcribe_id = _node_id(catalogue, "transcribe")
        extract_id = _node_id(catalogue, "extract_all")
        assert any(
            e["source"] == transcribe_id and e["target"] == extract_id
            for e in catalogue["edges"]
        ), "transcribe must flow into extract_all"

    def test_catalogue_has_final_catalogue_node_fed_by_merge(self):
        """The preset must end with a catalogue node so the workflow produces
        a unified Catalogue artifact, not just per-entity outputs (#720).

        Catalogue's only wired input is `data` from merge_extracts; the
        transcript is read from state.outputs by the tool itself so the
        node fires once on `data` arrival rather than twice (#837 follow-up).
        """
        presets = {p["name"]: p for p in _load_preset_files()}
        catalogue = presets["Catalogue"]

        node_tools = {n["tool"] for n in catalogue["nodes"]}
        assert "catalogue" in node_tools

        catalogue_id = _node_id(catalogue, "catalogue")
        data_feeders = [
            e for e in catalogue["edges"]
            if e["target"] == catalogue_id and e.get("target_port") == "data"
        ]
        assert data_feeders, "no edge feeds catalogue.data"
        assert {e["source"] for e in data_feeders} == {"merge_extracts"}

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

    def test_catalogue_uses_combined_extractor(self):
        """The Catalogue preset uses the single combined extract_all tool
        (one LLM call per page returns all six entity types) instead of six
        separate per-entity extractors. Per-type folder cleanup nodes still
        run downstream of the combined extractor."""
        presets = {p["name"]: p for p in _load_preset_files()}
        node_tools = {n["tool"] for n in presets["Catalogue"]["nodes"]}
        assert "extract_all" in node_tools, (
            "Catalogue preset must use the combined extract_all tool"
        )
        for cleaner in (
            "people_folder_cleanup",
            "places_folder_cleanup",
            "organizations_folder_cleanup",
            "dates_folder_cleanup",
            "events_folder_cleanup",
            "keywords_folder_cleanup",
        ):
            assert cleaner in node_tools, (
                f"Catalogue preset missing folder cleanup {cleaner!r}"
            )
        # Per-type extractors and per-page cleanups dropped for speed.
        for dropped in (
            "people_extract", "places_extract", "organizations_extract",
            "dates_extract", "events_extract", "keywords_extract",
            "people_page_cleanup", "places_page_cleanup",
            "organizations_page_cleanup", "dates_page_cleanup",
            "events_page_cleanup", "keywords_page_cleanup",
        ):
            assert dropped not in node_tools, (
                f"Catalogue preset should no longer use {dropped!r}"
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

    def test_catalogue_small_uses_dollar_small_throughout(self):
        """Every LLM-using node in the default Catalogue preset references
        the $small alias so users with different providers don't have to
        re-edit each node when their default model changes (#810).

        Transcribe is intentionally NOT aliased — it's a vision tool, so
        it falls back to the user's vision category default (e.g. Apple
        Vision OCR). Aliasing it to $small would route images to a
        text-only model.
        """
        presets = {p["name"]: p for p in _load_preset_files()}
        small_tools = {
            "extract_all", "catalogue",
            "people_folder_cleanup", "places_folder_cleanup",
            "organizations_folder_cleanup", "dates_folder_cleanup",
            "events_folder_cleanup", "keywords_folder_cleanup",
        }
        for node in presets["Catalogue"]["nodes"]:
            if node["tool"] in small_tools:
                assert node["config"].get("provider_name") == "$small", (
                    f"node {node['id']} ({node['tool']}) should use $small"
                )
        # Transcribe must not use the text alias.
        for node in presets["Catalogue"]["nodes"]:
            if node["tool"] == "transcribe":
                assert "provider_name" not in node["config"], (
                    "transcribe should fall back to the vision category "
                    "default — aliasing it to $small breaks Apple Vision OCR"
                )

    def test_catalogue_inputs_route_via_transcribe_not_user_aggregate(self):
        """Catalogue + extract_all + merge_extracts read directly from
        `transcribe`, NOT through a user-defined `aggregate` (Marshal
        page records) node.

        The previous wiring routed through a user `aggregate` node that
        LangGraph scheduled in the same super-step as the parallel
        transcribers. State is frozen within a super-step, so the user
        aggregate read an empty parallel_results snapshot and produced
        an empty payload — leaving catalogue and extract_all with no
        text input and the workflow aborting with 'No aggregated text
        provided' (#837).

        The auto-aggregator (transcribe_aggregate) handles fan-in
        correctly per LangGraph semantics: it fires AFTER all parallel
        sub-nodes complete, so any node downstream of `transcribe`
        sees the real aggregated text. By removing the redundant user
        aggregate, catalogue / extract_all / merge_extracts all land
        in the correct super-step with real data."""
        presets = {p["name"]: p for p in _load_preset_files()}
        for preset_name in ("Catalogue", "Catalogue (Mixed)"):
            preset = presets[preset_name]

            # No user-defined aggregate node should exist (only the
            # `merge_extracts` aggregate which fans-in cleanup outputs
            # AFTER extract_all has run).
            user_aggregate_nodes = [
                n for n in preset["nodes"]
                if n["tool"] == "aggregate" and n["id"] != "merge_extracts"
            ]
            assert not user_aggregate_nodes, (
                f"{preset_name}: removed the user aggregate (Marshal page "
                f"records) node to avoid the LangGraph super-step race; "
                f"unexpected aggregate(s) still present: "
                f"{[n['id'] for n in user_aggregate_nodes]}"
            )

            # catalogue has exactly one wired input (`data` from
            # merge_extracts). The transcript text is pulled out of
            # state.outputs by the catalogue tool itself so the node
            # only fires once — when `data` is ready — instead of
            # twice (#837 follow-up; multi-input nodes fire whenever
            # any input port is ready).
            cat_text_sources = {
                e["source"]
                for e in preset["edges"]
                if e["target"] == "catalogue"
                and e.get("target_port") == "text"
            }
            assert cat_text_sources == set(), (
                f"{preset_name}: catalogue.text edge should be removed "
                f"so the node fires once — got {cat_text_sources}"
            )

            # catalogue.data still sources from merge_extracts so the
            # LLM has cleaned entity lists alongside the raw text.
            cat_data_sources = {
                e["source"]
                for e in preset["edges"]
                if e["target"] == "catalogue"
                and e.get("target_port") == "data"
            }
            assert cat_data_sources == {"merge_extracts"}, (
                f"{preset_name}: catalogue.data must come from merge_extracts "
                f"(entity context) — got {cat_data_sources}"
            )

            # extract_all reads from transcribe via two ports: `text`
            # (concatenated, kept as a fallback) and `records`
            # ([{doc_id, text}, ...] — the per-page provenance carrier
            # that drives page-level KG + per-page artifacts, #701).
            ext_text_sources = {
                e["source"]
                for e in preset["edges"]
                if e["target"] == "extract_all"
                and e.get("target_port") == "text"
            }
            assert ext_text_sources == {"transcribe"}, (
                f"{preset_name}: extract_all.text must come from transcribe — "
                f"got {ext_text_sources}"
            )
            ext_records_sources = {
                e["source"]
                for e in preset["edges"]
                if e["target"] == "extract_all"
                and e.get("target_port") == "records"
            }
            assert ext_records_sources == {"transcribe"}, (
                f"{preset_name}: extract_all.records must come from transcribe "
                f"(per-page records for page-level KG) — got {ext_records_sources}"
            )

    def test_catalogue_mixed_promotes_narrative_to_dollar_large(self):
        """Catalogue (Mixed) keeps $small for extract/cleanup but promotes
        the catalogue narrative node to $large so users get frontier-
        quality writing on the one synthesis call per folder."""
        presets = {p["name"]: p for p in _load_preset_files()}
        assert "Catalogue (Mixed)" in presets, (
            "Catalogue (Mixed) preset should ship alongside Catalogue"
        )
        nodes_by_tool: dict[str, dict] = {}
        for node in presets["Catalogue (Mixed)"]["nodes"]:
            nodes_by_tool.setdefault(node["tool"], node)
        # Narrative step uses $large.
        assert nodes_by_tool["catalogue"]["config"].get("provider_name") == "$large"
        # Everything else stays $small (excluding transcribe — see above).
        for tool in (
            "extract_all",
            "people_folder_cleanup", "keywords_folder_cleanup",
        ):
            assert nodes_by_tool[tool]["config"].get("provider_name") == "$small", (
                f"{tool} should stay on $small in the Mixed preset"
            )


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
            "Catalogue (Mixed)",
            "Catalogue (composable)",
            "Catalogue (Apple Intelligence)",
            "Spanish Paleography (18th–19th C.)",
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
