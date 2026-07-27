"""
Tests for default workflow preset loading and seeding.

Seeding must be idempotent: running it twice on the same library inserts
presets once only. Presets must be loadable from the packaged resources
directory without hitting disk outside of the known presets location.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fichero.workflows.default_workflows import (
    _load_preset_files,
    seed_default_workflows,
)
from fichero.workflows.types import WorkflowDef
from fichero.workflows.validation import (
    validate_workflow_connections,
    validate_workflow_preflight,
)


class TestLoadPresetFiles:
    def test_discovers_shipped_presets(self):
        presets = _load_preset_files()
        # We ship at least Transcribe and Catalogue as 0.0.2 defaults.
        names = {p.get("name") for p in presets}
        assert "Transcribe" in names
        assert "Catalogue" in names

    def test_shipped_preset_names_are_unique(self):
        """Two preset JSON files must never ship the same name.

        Seed/install code keys workflows by name, so a duplicate would shadow
        one preset at load time and make force-reinstall/delete semantics
        unpredictable.
        """
        names = [preset["name"] for preset in _load_preset_files()]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        assert not duplicates, f"duplicate preset names in resources/: {duplicates}"

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

    def test_legacy_catalogue_duplicate_presets_do_not_ship(self):
        presets = {p["name"]: p for p in _load_preset_files()}
        removed = {
            "Catalogue Full Pipeline",
            "Catalogue Each",
            "Catalogue Stage 1 - Transcribe Pages",
            "Catalogue Stage 2 - Extract Entities + KG",
            "Catalogue Stage 3 - Catalogue Artifacts",
        }
        assert not (removed & set(presets))

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
        assert "kg_writer" not in node_tools, (
            "Catalogue preset must persist KG inline, not via kg_writer"
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
        extract_all_node = next(
            n for n in presets["Catalogue"]["nodes"] if n["tool"] == "extract_all"
        )
        assert extract_all_node["config"].get("persist_kg") is True
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
        extract_id = _node_id(presets["Catalogue"], "extract_all")
        assert not any(
            e["source"] == extract_id and e["source_port"] == "kg_payload"
            for e in presets["Catalogue"]["edges"]
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

    def test_ner_per_page_local_persists_kg_inline(self):
        presets = {p["name"]: p for p in _load_preset_files()}
        preset = presets["NER per-page (local)"]
        node_tools = {n["tool"] for n in preset["nodes"]}
        assert "kg_writer" not in node_tools
        extract_all_node = next(
            n for n in preset["nodes"] if n["tool"] == "extract_all"
        )
        assert extract_all_node["config"].get("persist_kg") is True
        extract_id = _node_id(preset, "extract_all")
        assert not any(
            e["source"] == extract_id and e["source_port"] == "kg_payload"
            for e in preset["edges"]
        )

    def test_reviewable_catalogue_stage_presets_ship_beside_catalogue(self):
        """Reviewable staged presets are additive; the full Catalogue preset
        remains unchanged while users can run transcription and entity/KG
        stages independently (#1669)."""
        presets = {p["name"]: p for p in _load_preset_files()}
        catalogue = presets["Catalogue"]
        stage0 = presets["1 · Import → Artifacts"]
        stage0b = presets["2 · Extract Entities"]
        stage0c = presets["3 · Extract SVO → Claims"]
        stage0d = presets["4 · Merge / Dedup"]
        stage0e = presets["5 · KG Persist / Finalize"]

        assert catalogue.get("is_template") is True
        assert catalogue.get("is_system") is True
        assert catalogue.get("folder_path") == "/Catalogue"
        assert "stage" not in catalogue.get("tags", [])
        assert "reviewable" not in catalogue.get("tags", [])

        for preset in (stage0, stage0b, stage0c, stage0d, stage0e):
            assert preset.get("is_template") is True
            assert preset.get("is_system") is True
            assert preset.get("folder_path") == "/Catalogue"
            assert "stage" in preset.get("tags", [])
            assert "reviewable" in preset.get("tags", [])

        stage0_tools = {n["tool"] for n in stage0["nodes"]}
        assert stage0_tools == {"files", "import_artifacts"}
        assert "import" in stage0.get("tags", [])
        import_node = next(n for n in stage0["nodes"] if n["tool"] == "import_artifacts")
        assert import_node["config"] == {}
        files_id = _node_id(stage0, "files")
        import_id = _node_id(stage0, "import_artifacts")
        assert any(
            e["source"] == files_id
            and e["target"] == import_id
            and e["source_port"] == "documents"
            and e["target_port"] == "documents"
            for e in stage0["edges"]
        ), "stage 0 must feed selected documents into import_artifacts"

        stage0b_tools = {n["tool"] for n in stage0b["nodes"]}
        assert stage0b_tools == {"files", "extract_entities_only"}
        extract_entities_node = next(
            n for n in stage0b["nodes"] if n["tool"] == "extract_entities_only"
        )
        assert extract_entities_node["config"].get("provider_name") == "$small"

        stage0c_tools = {n["tool"] for n in stage0c["nodes"]}
        assert stage0c_tools == {"files", "extract_svo_only"}
        assert "claims" in stage0c.get("tags", [])
        extract_svo_node = next(
            n for n in stage0c["nodes"] if n["tool"] == "extract_svo_only"
        )
        assert extract_svo_node["config"].get("provider_name") == "$small"
        files_id = _node_id(stage0c, "files")
        extract_svo_id = _node_id(stage0c, "extract_svo_only")
        assert any(
            e["source"] == files_id
            and e["target"] == extract_svo_id
            and e["source_port"] == "documents"
            and e["target_port"] == "documents"
            for e in stage0c["edges"]
        ), "stage 3 must feed selected documents into extract_svo_only"

        stage0d_tools = {n["tool"] for n in stage0d["nodes"]}
        assert stage0d_tools == {"files", "merge_dedup_only"}
        assert "merge" in stage0d.get("tags", [])
        assert "dedup" in stage0d.get("tags", [])
        merge_dedup_id = _node_id(stage0d, "merge_dedup_only")
        files_id = _node_id(stage0d, "files")
        assert any(
            e["source"] == files_id
            and e["target"] == merge_dedup_id
            and e["source_port"] == "documents"
            and e["target_port"] == "documents"
            for e in stage0d["edges"]
        ), "stage 4 must feed selected documents into merge_dedup_only"

        stage0e_tools = {n["tool"] for n in stage0e["nodes"]}
        assert stage0e_tools == {"files", "kg_persist_finalize"}
        assert "kg" in stage0e.get("tags", [])
        assert "finalize" in stage0e.get("tags", [])
        kg_finalize_id = _node_id(stage0e, "kg_persist_finalize")
        files_id = _node_id(stage0e, "files")
        assert any(
            e["source"] == files_id
            and e["target"] == kg_finalize_id
            and e["source_port"] == "documents"
            and e["target_port"] == "documents"
            for e in stage0e["edges"]
        ), "stage 5 must feed selected documents into kg_persist_finalize"

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

    def test_retired_duplicate_presets_do_not_ship(self):
        """Retired duplicate presets must not appear in shipped JSON (#2251).

        'Spanish Paleography (18th–19th C.)' merged into 'Transcribe Paleography'
        (language=auto).  The two multipass/v2 Spanish Script variants collapsed
        into a single 'Transcribe Spanish Script (19th-20th C.)' + its child.
        """
        presets = {p["name"]: p for p in _load_preset_files()}
        retired = {
            "Spanish Paleography (18th–19th C.)",
            "Transcribe Spanish Script (19th-20th C., Multi-Pass)",
            "Transcribe Spanish Script v2 (19th-20th C., Sub-Workflow)",
        }
        shipped = retired & set(presets)
        assert not shipped, f"retired presets still in resources/: {shipped}"

    def test_transcribe_paleography_uses_auto_language_on_pass1(self):
        """Transcribe Paleography Pass 1 must use language='auto' so it handles
        any language (Spanish, Latin, etc.) without the caller choosing (#2251).
        The old 'Spanish Paleography (18th–19th C.)' preset was language='es'
        and has been retired in favour of this unified, language-neutral preset."""
        presets = {p["name"]: p for p in _load_preset_files()}
        paleography = presets["Transcribe Paleography"]

        transcribe_node = next(
            n for n in paleography["nodes"] if n["tool"] == "transcribe"
        )
        assert transcribe_node["config"].get("language") == "auto", (
            "Transcribe Paleography Pass 1 must use language='auto' so it "
            "handles any script language without the caller selecting one"
        )

    def test_transcribe_paleography_is_two_pass_with_review(self):
        """Transcribe Paleography must keep its two-pass (draft + review) wiring."""
        presets = {p["name"]: p for p in _load_preset_files()}
        paleography = presets["Transcribe Paleography"]
        node_tools = {n["tool"] for n in paleography["nodes"]}
        assert "transcribe" in node_tools
        assert "transcribe_review" in node_tools
        assert "extract_all" not in node_tools

    def test_transcribe_presets_query_reference_corpus_on_pass_two(self):
        """The shipped transcription presets feed Pass 1 into corpus search.

        Pass 2 should receive the search hits as metadata so the review
        prompt can inspect the reference corpus alongside the draft.
        """
        presets = {p["name"]: p for p in _load_preset_files()}
        preset_specs = [
            ("Transcribe HTR", "transcribe", "transcribe_review", "reference-search"),
            (
                "Transcribe Paleography",
                "transcribe",
                "transcribe_review",
                "reference-search",
            ),
            (
                "Spanish Script v2 Child Passes (19th-20th C.)",
                "transcribe-draft",
                "transcribe-review-medium",
                "reference-search",
            ),
            ("Transcribe (Auto-Detect)", "transcribe-htr", "review-htr", "reference-search-htr"),
            (
                "Transcribe (Auto-Detect)",
                "transcribe-paleo",
                "review-paleo",
                "reference-search-paleo",
            ),
        ]

        for preset_name, transcribe_id, review_id, search_id in preset_specs:
            preset = presets[preset_name]
            node_ids = {n["id"] for n in preset["nodes"]}
            assert search_id in node_ids, f"{preset_name} must include {search_id}"

            transcribe_to_search = next(
                e
                for e in preset["edges"]
                if e["source"] == transcribe_id and e["target"] == search_id
            )
            assert transcribe_to_search["source_port"] == "text"
            assert transcribe_to_search["target_port"] == "query"

            search_to_review = next(
                e
                for e in preset["edges"]
                if e["source"] == search_id and e["target"] == review_id
            )
            assert search_to_review["source_port"] == "documents"
            assert search_to_review["target_port"] == "metadata"

    def test_search_tool_declares_query_input_port(self):
        """The `search` tool must expose a `query` INPUT port, not just a
        `query` config field.

        The shipped transcription presets feed a draft transcription into the
        reference-search node via a `text -> query` edge, and the tool's run
        function reads `inputs.get("query")`. When the ToolDef declared
        `input_ports=[]`, execution-time graph validation rejected that edge
        with "unknown target port 'query' on node 'reference-search'" and the
        workflow 400'd. Guard the port declaration so the edge stays valid.
        """
        from fichero.workflows.registry import TOOL_DEFS

        search_def = TOOL_DEFS["search"]
        query_ports = [p for p in search_def.input_ports if p.id == "query"]
        assert query_ports, (
            "search tool must declare a 'query' input port — the transcription "
            "presets feed the draft transcription into it via a text->query edge"
        )
        assert query_ports[0].data_type.value == "text"

    def test_paleography_ensemble_passes_execution_gate(self):
        """The ensemble preset must pass the exact validation the /execute
        endpoint runs, so it never ships broken again (#3905 follow-up).

        Two regressions shipped past the smoke harness (which stubs every tool
        and `resolve_model_alias`, bypassing both validators):
          1. the reference-search `text -> query` edge hit an undeclared port;
          2. the T5 translate node used the vision-tier `$vision_medium` alias.
        This mirrors `_validate_workflow_for_execution`: load via
        `to_workflow_def` and run both validators, asserting zero errors.
        """
        from fichero.models import Workflow
        from fichero.workflows.runtime import to_workflow_def

        preset = {
            p["name"]: p for p in _load_preset_files()
        }["Transcribe Paleography (Ensemble + Deep Review)"]
        workflow_def = to_workflow_def(
            Workflow(
                id="ensemble-gate-regression",
                name=preset["name"],
                description=preset.get("description", ""),
                nodes=preset["nodes"],
                edges=preset["edges"],
                config=preset.get("config", {}),
                folder_path=preset.get("folder_path", "/"),
            )
        )

        connection_errors = validate_workflow_connections(workflow_def)
        preflight_errors = validate_workflow_preflight(workflow_def)

        # Focused checks on the exact two failure modes that shipped. The
        # capability-mismatch check fires before any app_db lookup, so the
        # vision-tier assertion is independent of whether AI Defaults are
        # configured in the test environment (full-resolution preflight with
        # configured defaults is exercised in test_vision_alias_preflight.py).
        assert not any(
            "unknown target port 'query'" in err for err in connection_errors
        ), f"reference-search query edge regressed: {connection_errors}"
        assert not any(
            "vision-tier model alias" in err for err in preflight_errors
        ), f"a text node regressed onto a vision-tier alias: {preflight_errors}"

        # The connection graph must be fully clean (environment-independent).
        assert connection_errors == []

    def test_paleography_ensemble_translate_uses_text_tier_alias(self):
        """The ensemble's T5 translate node is a text (llm) tool, so it must use
        a text-tier alias ($small/$medium/$large), never a $vision_* alias."""
        presets = {p["name"]: p for p in _load_preset_files()}
        ensemble = presets["Transcribe Paleography (Ensemble + Deep Review)"]
        translate_node = next(
            n for n in ensemble["nodes"] if n["tool"] == "translate"
        )
        alias = translate_node["config"].get("provider_name")
        assert alias in {"$small", "$medium", "$large"}, (
            f"translate node must use a text-tier alias, got {alias!r}"
        )
        assert not alias.startswith("$vision_"), (
            "translate is a text node; a $vision_* alias fails preflight"
        )

    def test_spanish_script_subworkflow_ships_in_transcribe_folder(self):
        """After rationalization (#2251), the sole user-facing Spanish Script preset
        is 'Transcribe Spanish Script (19th-20th C.)' (renamed from v2 sub-workflow).
        It must ship alongside its child component."""
        presets = {p["name"]: p for p in _load_preset_files()}

        parent = presets["Transcribe Spanish Script (19th-20th C.)"]
        child = presets["Spanish Script v2 Child Passes (19th-20th C.)"]

        for preset in (child, parent):
            assert preset.get("is_template") is True
            assert preset.get("is_system") is True
            assert preset.get("folder_path") == "/Transcribe"
            assert "sub-workflow" in preset.get("tags", [])

        # "v2" tag dropped from parent — only child keeps it via legacy
        assert "v2" not in parent.get("tags", [])
        # Preset version bumped on rename
        assert parent.get("config", {}).get("preset_version") == 2

    def test_spanish_script_v2_child_uses_distinct_vision_tiers(self):
        presets = {p["name"]: p for p in _load_preset_files()}
        child = presets["Spanish Script v2 Child Passes (19th-20th C.)"]
        node_by_id = {node["id"]: node for node in child["nodes"]}

        assert node_by_id["transcribe-draft"]["config"]["provider_name"] == "$vision_small"
        assert (
            node_by_id["transcribe-review-medium"]["config"]["provider_name"]
            == "$vision_medium"
        )
        assert (
            node_by_id["transcribe-final-large"]["config"]["provider_name"]
            == "$vision_large"
        )
        # files + documents both forwarded from the sub-workflow inputs so each
        # PAGE gets its own per-page transcription artifact (#2523), not the
        # parent PDF. Mirrors the gold-standard HTR documents-port wiring.
        assert node_by_id["transcribe-draft"]["inputs"] == {
            "files": "$.inputs.files",
            "documents": "$.inputs.documents",
        }
        assert node_by_id["transcribe-review-medium"]["inputs"] == {
            "files": "$.inputs.files",
            "documents": "$.inputs.documents",
        }
        assert node_by_id["transcribe-final-large"]["inputs"] == {
            "files": "$.inputs.files",
            "documents": "$.inputs.documents",
        }

        assert node_by_id["transcribe-final-large"]["config"]["update_page_content"] is True
        assert node_by_id["transcribe-review-medium"]["config"]["update_page_content"] is False

    def test_spanish_script_v2_parent_composes_child_with_typed_contract(self):
        presets = {p["name"]: p for p in _load_preset_files()}
        child = WorkflowDef(**presets["Spanish Script v2 Child Passes (19th-20th C.)"])
        parent_data = presets["Transcribe Spanish Script (19th-20th C.)"]
        parent = WorkflowDef(**parent_data)

        node_by_id = {node["id"]: node for node in parent_data["nodes"]}
        sub_node = node_by_id["spanish-script-v2"]
        config = sub_node["config"]

        assert sub_node["tool"] == "sub_workflow"
        assert config["workflow_ref"] == child.name
        assert config["input_contract"] == [
            {
                "id": "files",
                "data_type": "files",
                "required": True,
                "description": "Selected page image paths to transcribe.",
            },
            {
                "id": "documents",
                "data_type": "any",
                "required": False,
                "description": (
                    "Per-page document metadata (index-aligned with files) so "
                    "each page gets its own transcription artifact instead of "
                    "the parent PDF."
                ),
            },
        ]
        # The parent must forward the selected documents into the sub-workflow
        # so the per-page fix (#2523) survives the sub-workflow boundary.
        assert any(
            edge["source"] == "files-source"
            and edge["target"] == "spanish-script-v2"
            and edge["source_port"] == "documents"
            and edge["target_port"] == "documents"
            for edge in parent_data["edges"]
        )
        assert config["output_contract"] == [
            {
                "id": "text",
                "data_type": "text",
                "required": True,
                "description": "Final reconciled transcription text.",
            }
        ]
        assert config["output_mapping"] == {
            "text": "$.nodes.transcribe-final-large.text"
        }
        assert any(
            edge["source"] == "files-source"
            and edge["target"] == "spanish-script-v2"
            and edge["source_port"] == "files"
            and edge["target_port"] == "files"
            for edge in parent_data["edges"]
        )
        assert validate_workflow_preflight(
            parent,
            workflow_resolver=lambda ref: child if ref == child.name else None,
        ) == []

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
        for preset_name in ("Catalogue",):
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


    def test_auto_detect_preset_wiring(self):
        """Auto-detect preset: classify_script node + route_map edge covering all 4 profiles."""
        presets = {p["name"]: p for p in _load_preset_files()}
        ad = presets["Transcribe (Auto-Detect)"]

        node_tools = {n["tool"] for n in ad["nodes"]}
        assert "classify_script" in node_tools
        assert "transcribe" in node_tools
        assert "transcribe_review" in node_tools

        # Must have exactly one route_map edge
        route_edges = [e for e in ad["edges"] if e.get("route_map")]
        assert len(route_edges) == 1, "auto-detect must have exactly one route_map edge"

        rmap = route_edges[0]["route_map"]
        assert set(rmap.keys()) == {
            "typescript",
            "manuscript",
            "htr",
            "paleography",
            "mixed",
        }
        assert rmap["mixed"] == rmap["paleography"]

        # All route_map target node IDs must exist in nodes
        node_ids = {n["id"] for n in ad["nodes"]}
        for key, target_id in rmap.items():
            assert target_id in node_ids, f"route_map[{key!r}] → {target_id!r} not in nodes"

        # Two-pass branches (HTR, paleography) must have a review node downstream
        htr_transcribe_id = rmap["htr"]
        paleo_transcribe_id = rmap["paleography"]
        # Find review nodes connected from htr/paleo transcribe nodes
        htr_review_edges = [e for e in ad["edges"] if e.get("source") == htr_transcribe_id and e.get("target_port") == "context"]
        paleo_review_edges = [e for e in ad["edges"] if e.get("source") == paleo_transcribe_id and e.get("target_port") == "context"]
        assert htr_review_edges, "HTR branch must chain to a review node via context port"
        assert paleo_review_edges, "Paleography branch must chain to a review node via context port"

    def test_auto_detect_branch_nodes_have_files_input(self):
        """Branch transcribe/review nodes pull files explicitly from files-source
        via inputs (not edges) since they are not directly wired from files-source."""
        presets = {p["name"]: p for p in _load_preset_files()}
        ad = presets["Transcribe (Auto-Detect)"]

        route_edges = [e for e in ad["edges"] if e.get("route_map")]
        routed_ids = set(route_edges[0]["route_map"].values())

        for node in ad["nodes"]:
            if node["id"] not in routed_ids:
                continue
            inputs = node.get("inputs", {})
            assert "files" in inputs, (
                f"branch node {node['id']!r} must declare inputs.files "
                f"to receive files without a direct graph edge"
            )
            assert inputs["files"] == "$.nodes.files-source.files"

    def test_auto_detect_branch_nodes_have_documents_input(self):
        """Branch transcribe/review nodes must carry per-page documents too,
        or page-content/artifact writes fall back to the parent PDF."""
        presets = {p["name"]: p for p in _load_preset_files()}
        ad = presets["Transcribe (Auto-Detect)"]

        route_edges = [e for e in ad["edges"] if e.get("route_map")]
        routed_ids = set(route_edges[0]["route_map"].values())
        review_ids = {
            e["target"]
            for e in ad["edges"]
            if e.get("target_port") == "context"
        }

        for node in ad["nodes"]:
            if node["id"] not in routed_ids | review_ids:
                continue
            inputs = node.get("inputs", {})
            assert "documents" in inputs, (
                f"branch node {node['id']!r} must declare inputs.documents "
                f"for per-page document attribution"
            )
            assert inputs["documents"] == "$.nodes.files-source.documents"

    def test_rotate_auto_orient_images_preset_wiring(self):
        """Rotate / Auto-Orient Images should expose the non-destructive
        rotate_images tool as a stageable default workflow (#1387)."""
        presets = {p["name"]: p for p in _load_preset_files()}
        assert "Rotate / Auto-Orient Images" in presets, "rotate preset must ship"
        preset = presets["Rotate / Auto-Orient Images"]

        assert preset.get("is_template") is True
        assert preset.get("is_system") is True
        assert preset.get("folder_path") == "/Image Editing"
        assert preset.get("format") == "nodes"

        node_tools = {n["tool"] for n in preset["nodes"]}
        for tool in ("files", "rotate_images"):
            assert tool in node_tools, f"preset missing {tool!r} node"

        files_id = _node_id(preset, "files")
        rotate_id = _node_id(preset, "rotate_images")
        assert any(
            e["source"] == files_id
            and e["target"] == rotate_id
            and e["source_port"] == "files"
            and e["target_port"] == "files"
            for e in preset["edges"]
        ), "files must flow into rotate_images"
        assert any(
            e["source"] == files_id
            and e["target"] == rotate_id
            and e["source_port"] == "documents"
            and e["target_port"] == "documents"
            for e in preset["edges"]
        ), "documents must flow into rotate_images for preview editor updates"

        rotate_node = next(n for n in preset["nodes"] if n["tool"] == "rotate_images")
        assert rotate_node["config"].get("auto_orient") is True
        assert rotate_node["config"].get("rotation_degrees") == 0
        assert rotate_node["config"].get("output_format") == "jpg"

    def test_enhance_images_preset_wiring(self):
        """Enhance Images should expose contrast/sharpness/denoise controls
        as a default image-editing workflow (#1388)."""
        presets = {p["name"]: p for p in _load_preset_files()}
        assert "Enhance Images" in presets, "enhance preset must ship"
        preset = presets["Enhance Images"]

        assert preset.get("is_template") is True
        assert preset.get("is_system") is True
        assert preset.get("folder_path") == "/Image Editing"
        assert preset.get("format") == "nodes"

        node_tools = {n["tool"] for n in preset["nodes"]}
        for tool in ("files", "enhance_images"):
            assert tool in node_tools, f"preset missing {tool!r} node"

        files_id = _node_id(preset, "files")
        enhance_id = _node_id(preset, "enhance_images")
        assert any(
            e["source"] == files_id
            and e["target"] == enhance_id
            and e["source_port"] == "files"
            and e["target_port"] == "files"
            for e in preset["edges"]
        ), "files must flow into enhance_images"
        assert any(
            e["source"] == files_id
            and e["target"] == enhance_id
            and e["source_port"] == "documents"
            and e["target_port"] == "documents"
            for e in preset["edges"]
        ), "documents must flow into enhance_images for preview editor updates"

        enhance_node = next(n for n in preset["nodes"] if n["tool"] == "enhance_images")
        assert enhance_node["config"].get("contrast") == 1.25
        assert enhance_node["config"].get("sharpness") == 1.1
        assert enhance_node["config"].get("denoise") is True
        assert enhance_node["config"].get("output_format") == "jpg"

    def test_fuzzy_clean_images_preset_wiring(self):
        """Fuzzy Clean Images should expose despeckle/background cleanup
        as a default image-editing workflow (#1389)."""
        presets = {p["name"]: p for p in _load_preset_files()}
        assert "Fuzzy Clean Images" in presets, "fuzzy clean preset must ship"
        preset = presets["Fuzzy Clean Images"]

        assert preset.get("is_template") is True
        assert preset.get("is_system") is True
        assert preset.get("folder_path") == "/Image Editing"
        assert preset.get("format") == "nodes"

        node_tools = {n["tool"] for n in preset["nodes"]}
        for tool in ("files", "fuzzy_clean_images"):
            assert tool in node_tools, f"preset missing {tool!r} node"

        files_id = _node_id(preset, "files")
        clean_id = _node_id(preset, "fuzzy_clean_images")
        assert any(
            e["source"] == files_id
            and e["target"] == clean_id
            and e["source_port"] == "files"
            and e["target_port"] == "files"
            for e in preset["edges"]
        ), "files must flow into fuzzy_clean_images"
        assert any(
            e["source"] == files_id
            and e["target"] == clean_id
            and e["source_port"] == "documents"
            and e["target_port"] == "documents"
            for e in preset["edges"]
        ), "documents must flow into fuzzy_clean_images for preview editor updates"

        clean_node = next(n for n in preset["nodes"] if n["tool"] == "fuzzy_clean_images")
        assert clean_node["config"].get("despeckle_radius") == 3
        assert clean_node["config"].get("background_clean") is True
        assert clean_node["config"].get("output_format") == "jpg"

    def test_remove_background_images_preset_wiring(self):
        """Remove Background Images should expose alpha-background removal
        as a default image-editing workflow (#1393)."""
        presets = {p["name"]: p for p in _load_preset_files()}
        assert "Remove Background Images" in presets, "remove background preset must ship"
        preset = presets["Remove Background Images"]

        assert preset.get("is_template") is True
        assert preset.get("is_system") is True
        assert preset.get("folder_path") == "/Image Editing"
        assert preset.get("format") == "nodes"

        node_tools = {n["tool"] for n in preset["nodes"]}
        for tool in ("files", "remove_background_images"):
            assert tool in node_tools, f"preset missing {tool!r} node"

        files_id = _node_id(preset, "files")
        remove_id = _node_id(preset, "remove_background_images")
        assert any(
            e["source"] == files_id
            and e["target"] == remove_id
            and e["source_port"] == "files"
            and e["target_port"] == "files"
            for e in preset["edges"]
        ), "files must flow into remove_background_images"
        assert any(
            e["source"] == files_id
            and e["target"] == remove_id
            and e["source_port"] == "documents"
            and e["target_port"] == "documents"
            for e in preset["edges"]
        ), "documents must flow into remove_background_images for preview editor updates"

        remove_node = next(n for n in preset["nodes"] if n["tool"] == "remove_background_images")
        assert remove_node["config"].get("method") == "threshold"
        assert remove_node["config"].get("threshold") == 28
        assert remove_node["config"].get("output_format") == "png"

    def test_segment_images_preset_wiring(self):
        """Segment Images should expose foreground-region segmentation
        as a default image-editing workflow (#1391)."""
        presets = {p["name"]: p for p in _load_preset_files()}
        assert "Segment Images" in presets, "segment preset must ship"
        preset = presets["Segment Images"]

        assert preset.get("is_template") is True
        assert preset.get("is_system") is True
        assert preset.get("folder_path") == "/Image Editing"
        assert preset.get("format") == "nodes"

        node_tools = {n["tool"] for n in preset["nodes"]}
        for tool in ("files", "segment_images"):
            assert tool in node_tools, f"preset missing {tool!r} node"

        files_id = _node_id(preset, "files")
        segment_id = _node_id(preset, "segment_images")
        assert any(
            e["source"] == files_id
            and e["target"] == segment_id
            and e["source_port"] == "files"
            and e["target_port"] == "files"
            for e in preset["edges"]
        ), "files must flow into segment_images"
        assert any(
            e["source"] == files_id
            and e["target"] == segment_id
            and e["source_port"] == "documents"
            and e["target_port"] == "documents"
            for e in preset["edges"]
        ), "documents must flow into segment_images for preview editor updates"

        segment_node = next(n for n in preset["nodes"] if n["tool"] == "segment_images")
        assert segment_node["config"].get("method") == "foreground"
        assert segment_node["config"].get("threshold") == 28
        assert segment_node["config"].get("output_format") == "png"

    def test_recombine_segments_preset_wiring(self):
        """Recombine Segments should ship as a default image-editing workflow (#1392)."""
        presets = {p["name"]: p for p in _load_preset_files()}
        assert "Recombine Segments" in presets, "recombine preset must ship"
        preset = presets["Recombine Segments"]

        assert preset.get("is_template") is True
        assert preset.get("is_system") is True
        assert preset.get("folder_path") == "/Image Editing"
        assert preset.get("format") == "nodes"

        node_tools = {n["tool"] for n in preset["nodes"]}
        for tool in ("files", "recombine_segments"):
            assert tool in node_tools, f"preset missing {tool!r} node"

        files_id = _node_id(preset, "files")
        recombine_id = _node_id(preset, "recombine_segments")
        assert any(
            e["source"] == files_id
            and e["target"] == recombine_id
            and e["source_port"] == "files"
            and e["target_port"] == "files"
            for e in preset["edges"]
        ), "files must flow into recombine_segments"

        recombine_node = next(n for n in preset["nodes"] if n["tool"] == "recombine_segments")
        assert recombine_node["config"].get("layout") == "vertical"
        assert recombine_node["config"].get("output_format") == "png"

    def test_split_images_preset_wiring(self):
        """Split Images should ship as a default image-editing workflow (#1394)."""
        presets = {p["name"]: p for p in _load_preset_files()}
        assert "Split Images" in presets, "split preset must ship"
        preset = presets["Split Images"]

        assert preset.get("is_template") is True
        assert preset.get("is_system") is True
        assert preset.get("folder_path") == "/Image Editing"
        assert preset.get("format") == "nodes"

        node_tools = {n["tool"] for n in preset["nodes"]}
        for tool in ("files", "split_images"):
            assert tool in node_tools, f"preset missing {tool!r} node"

        files_id = _node_id(preset, "files")
        split_id = _node_id(preset, "split_images")
        assert any(
            e["source"] == files_id
            and e["target"] == split_id
            and e["source_port"] == "files"
            and e["target_port"] == "files"
            for e in preset["edges"]
        ), "files must flow into split_images"

        split_node = next(n for n in preset["nodes"] if n["tool"] == "split_images")
        assert split_node["config"].get("rows") == 1
        assert split_node["config"].get("columns") == 2
        assert split_node["config"].get("output_format") == "png"

    def test_prepare_images_for_ocr_preset_wiring(self):
        """Prepare Images for OCR should expose the non-destructive image prep
        tool as a stageable default workflow (#1390)."""
        presets = {p["name"]: p for p in _load_preset_files()}
        assert "Prepare Images for OCR" in presets, "Prepare Images preset must ship"
        preset = presets["Prepare Images for OCR"]

        assert preset.get("is_template") is True
        assert preset.get("is_system") is True
        assert preset.get("folder_path") == "/Transcribe"
        assert preset.get("format") == "nodes"

        node_tools = {n["tool"] for n in preset["nodes"]}
        for tool in ("files", "prepare_images"):
            assert tool in node_tools, f"preset missing {tool!r} node"

        files_id = _node_id(preset, "files")
        prepare_id = _node_id(preset, "prepare_images")
        assert any(
            e["source"] == files_id
            and e["target"] == prepare_id
            and e["source_port"] == "files"
            and e["target_port"] == "files"
            for e in preset["edges"]
        ), "files must flow into prepare_images"
        assert any(
            e["source"] == files_id
            and e["target"] == prepare_id
            and e["source_port"] == "documents"
            and e["target_port"] == "documents"
            for e in preset["edges"]
        ), "documents should flow into prepare_images for future editor integration"

        prepare_node = next(n for n in preset["nodes"] if n["tool"] == "prepare_images")
        assert prepare_node["config"].get("output_format") == "jpg"
        assert prepare_node["config"].get("compression_quality") == 85
        assert prepare_node["config"].get("grayscale") is True
        assert prepare_node["config"].get("autocontrast") is True
        assert prepare_node["config"].get("pdf_dpi") == 300

    def test_capture_ocr_transcribe_preset_wiring(self):
        """Capture OCR + Transcribe should preserve original document linkage
        while staging OCR-friendly derived images for capture uploads (#2356)."""
        presets = {p["name"]: p for p in _load_preset_files()}
        assert "Capture OCR + Transcribe" in presets, "capture OCR preset must ship"
        preset = presets["Capture OCR + Transcribe"]

        assert preset.get("is_template") is True
        assert preset.get("is_system") is True
        assert preset.get("folder_path") == "/Transcribe"
        assert preset.get("format") == "nodes"

        node_tools = {n["tool"] for n in preset["nodes"]}
        for tool in ("files", "prepare_images", "enhance_images", "transcribe"):
            assert tool in node_tools, f"preset missing {tool!r} node"

        files_id = _node_id(preset, "files")
        prepare_id = _node_id(preset, "prepare_images")
        enhance_id = _node_id(preset, "enhance_images")
        transcribe_id = _node_id(preset, "transcribe")

        assert any(
            e["source"] == files_id
            and e["target"] == prepare_id
            and e["source_port"] == "files"
            and e["target_port"] == "files"
            for e in preset["edges"]
        ), "files must flow into prepare_images"
        assert any(
            e["source"] == files_id
            and e["target"] == prepare_id
            and e["source_port"] == "documents"
            and e["target_port"] == "documents"
            for e in preset["edges"]
        ), "documents must flow into prepare_images"
        assert any(
            e["source"] == prepare_id
            and e["target"] == enhance_id
            and e["source_port"] == "output_files"
            and e["target_port"] == "files"
            for e in preset["edges"]
        ), "prepared derived files must flow into enhance_images"
        assert any(
            e["source"] == files_id
            and e["target"] == transcribe_id
            and e["source_port"] == "documents"
            and e["target_port"] == "documents"
            for e in preset["edges"]
        ), "original documents must flow into transcribe for page-content persistence"
        assert any(
            e["source"] == enhance_id
            and e["target"] == transcribe_id
            and e["source_port"] == "output_files"
            and e["target_port"] == "files"
            for e in preset["edges"]
        ), "enhanced derived files must flow into transcribe"

        transcribe_node = next(n for n in preset["nodes"] if n["tool"] == "transcribe")
        assert transcribe_node["config"].get("vision_mode") == "auto"
        assert transcribe_node["config"].get("language") == "auto"
        assert transcribe_node["config"].get("update_page_content") is True
        assert transcribe_node["config"].get("save_to_db") is True

    def test_describe_visual_preset_wires_documents(self):
        """Describe (visual) must wire per-page documents so descriptions land
        on page children, never the parent PDF."""
        presets = {p["name"]: p for p in _load_preset_files()}
        assert "Describe (visual)" in presets, "describe visual preset must ship"
        preset = presets["Describe (visual)"]

        files_id = _node_id(preset, "files")
        describe_id = _node_id(preset, "describe")

        assert any(
            e["source"] == files_id
            and e["target"] == describe_id
            and e["source_port"] == "files"
            and e["target_port"] == "files"
            for e in preset["edges"]
        ), "files must flow into describe"
        assert any(
            e["source"] == files_id
            and e["target"] == describe_id
            and e["source_port"] == "documents"
            and e["target_port"] == "documents"
            for e in preset["edges"]
        ), "documents must flow into describe for per-page attribution"

    def test_clean_up_text_preset_wiring(self):
        """Clean Up Text preset: files → transcribe → clean_text.

        Transcribe is the universal text source (it reuses an existing text
        layer for digital PDFs, #1033), so the preset works on any doc or
        folder. clean_text then cleans the extracted text.
        """
        presets = {p["name"]: p for p in _load_preset_files()}
        assert "Clean Up Text" in presets, "Clean Up Text preset must ship"
        preset = presets["Clean Up Text"]

        assert preset.get("is_template") is True
        assert preset.get("is_system") is True
        assert preset.get("folder_path") == "/Clean Up"
        assert preset.get("format") == "nodes"

        node_tools = {n["tool"] for n in preset["nodes"]}
        for tool in ("files", "transcribe", "clean_text"):
            assert tool in node_tools, f"preset missing {tool!r} node"

        files_id = _node_id(preset, "files")
        transcribe_id = _node_id(preset, "transcribe")
        clean_id = _node_id(preset, "clean_text")

        # files → transcribe (files port).
        assert any(
            e["source"] == files_id
            and e["target"] == transcribe_id
            and e["source_port"] == "files"
            and e["target_port"] == "files"
            for e in preset["edges"]
        ), "files must flow into transcribe"

        # transcribe.text → clean_text.text.
        assert any(
            e["source"] == transcribe_id
            and e["target"] == clean_id
            and e["source_port"] == "text"
            and e["target_port"] == "text"
            for e in preset["edges"]
        ), "transcribe text must flow into clean_text"

    def test_clean_up_text_model_aliasing(self):
        """clean_text uses the $small alias; transcribe stays on the vision
        default (no provider alias) so Apple Vision OCR isn't broken (#810)."""
        presets = {p["name"]: p for p in _load_preset_files()}
        preset = presets["Clean Up Text"]

        clean_node = next(n for n in preset["nodes"] if n["tool"] == "clean_text")
        assert clean_node["config"].get("provider_name") == "$small"

        transcribe_node = next(
            n for n in preset["nodes"] if n["tool"] == "transcribe"
        )
        assert "provider_name" not in transcribe_node.get("config", {}), (
            "transcribe must use the vision category default, not $small"
        )

    def test_translate_preset_wiring(self):
        """One-step Translate preset: files → transcribe → text_translate.

        Transcribe is the universal text source (it reuses an existing text
        layer for digital PDFs, #1033); text_translate then translates the
        extracted text into the configured target language (#926).
        """
        presets = {p["name"]: p for p in _load_preset_files()}
        assert "Translate" in presets, "Translate preset must ship"
        preset = presets["Translate"]

        assert preset.get("is_template") is True
        assert preset.get("is_system") is True
        assert preset.get("folder_path") == "/Translate"
        assert preset.get("format") == "nodes"

        node_tools = {n["tool"] for n in preset["nodes"]}
        for tool in ("files", "transcribe", "text_translate"):
            assert tool in node_tools, f"preset missing {tool!r} node"

        files_id = _node_id(preset, "files")
        transcribe_id = _node_id(preset, "transcribe")
        translate_id = _node_id(preset, "text_translate")

        assert any(
            e["source"] == files_id
            and e["target"] == transcribe_id
            and e["source_port"] == "files"
            and e["target_port"] == "files"
            for e in preset["edges"]
        ), "files must flow into transcribe"

        assert any(
            e["source"] == transcribe_id
            and e["target"] == translate_id
            and e["source_port"] == "text"
            and e["target_port"] == "text"
            for e in preset["edges"]
        ), "transcribe text must flow into text_translate"

    def test_translate_preset_target_language_is_editable_config(self):
        """The target language ships as node config (editable), not baked into
        the tool — and defaults to English for Daniel (#926)."""
        presets = {p["name"]: p for p in _load_preset_files()}
        translate_node = next(
            n for n in presets["Translate"]["nodes"] if n["tool"] == "text_translate"
        )
        assert translate_node["config"].get("target_language") == "English"
        assert translate_node["config"].get("provider_name") == "$small"

        transcribe_node = next(
            n for n in presets["Translate"]["nodes"] if n["tool"] == "transcribe"
        )
        assert "provider_name" not in transcribe_node.get("config", {}), (
            "transcribe must use the vision category default, not $small"
        )

    def test_translate_review_preset_wiring(self):
        """Multi-step Translate + Double-Check preset (#926):
        files → transcribe → text_translate → text_translate_review.

        The reviewer takes the draft via the single graph edge (so it fires
        AFTER translate, never on a half-built draft — the #837 fan-in race)
        and pulls the ORIGINAL source via a static input path to transcribe.
        """
        presets = {p["name"]: p for p in _load_preset_files()}
        assert "Translate + Double-Check" in presets, (
            "Translate + Double-Check preset must ship"
        )
        preset = presets["Translate + Double-Check"]

        assert preset.get("is_template") is True
        assert preset.get("is_system") is True
        assert preset.get("folder_path") == "/Translate"

        node_tools = {n["tool"] for n in preset["nodes"]}
        for tool in ("files", "transcribe", "text_translate", "text_translate_review"):
            assert tool in node_tools, f"preset missing {tool!r} node"

        transcribe_id = _node_id(preset, "transcribe")
        translate_id = _node_id(preset, "text_translate")
        review_id = _node_id(preset, "text_translate_review")

        # Pass 1: transcribe.text → text_translate.text.
        assert any(
            e["source"] == transcribe_id
            and e["target"] == translate_id
            and e["source_port"] == "text"
            and e["target_port"] == "text"
            for e in preset["edges"]
        ), "transcribe text must flow into text_translate"

        # Pass 2: the draft flows via the ONLY graph edge into review,
        # so review depends on (fires after) translate.
        review_edges = [e for e in preset["edges"] if e["target"] == review_id]
        assert len(review_edges) == 1, (
            "review must have exactly one incoming edge (the draft) to avoid "
            "the multi-input fan-in race (#837)"
        )
        draft_edge = review_edges[0]
        assert draft_edge["source"] == translate_id
        assert draft_edge["source_port"] == "text"
        assert draft_edge["target_port"] == "text"

        # The original source reaches review via a static input path, NOT a
        # second graph edge — so it doesn't gate when the node fires.
        review_node = next(n for n in preset["nodes"] if n["id"] == review_id)
        assert review_node["inputs"].get("context") == "$.nodes.transcribe.text", (
            "review must pull the original source from transcribe via a static "
            "input path so the node still fires once, after translate"
        )

    def test_translate_review_preset_model_aliasing(self):
        """Both LLM passes use the $small alias; transcribe stays on the
        vision default (no provider alias) so Apple Vision OCR isn't broken."""
        presets = {p["name"]: p for p in _load_preset_files()}
        preset = presets["Translate + Double-Check"]

        for tool in ("text_translate", "text_translate_review"):
            node = next(n for n in preset["nodes"] if n["tool"] == tool)
            assert node["config"].get("provider_name") == "$small", (
                f"{tool} should use the $small alias"
            )

        transcribe_node = next(
            n for n in preset["nodes"] if n["tool"] == "transcribe"
        )
        assert "provider_name" not in transcribe_node.get("config", {})

    def test_translate_deepl_preset_wiring(self):
        """Provider-driven translation preset uses the `translate` tool with
        explicit DeepL provider defaults for Dutch→English workflows (#1332)."""
        presets = {p["name"]: p for p in _load_preset_files()}
        assert "Translate (DeepL)" in presets, "Translate (DeepL) preset must ship"
        preset = presets["Translate (DeepL)"]

        node_tools = {n["tool"] for n in preset["nodes"]}
        for tool in ("files", "transcribe", "translate"):
            assert tool in node_tools, f"preset missing {tool!r} node"

        translate_node = next(n for n in preset["nodes"] if n["tool"] == "translate")
        assert translate_node["config"].get("provider_name") == "deepl"
        assert translate_node["config"].get("source_lang") == "nl"
        assert translate_node["config"].get("target_lang") == "en"


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
        # Discover preset names directly from the JSON files so this test
        # stays green automatically when new presets are added.
        all_preset_names = [p["name"] for p in _load_preset_files()]
        db = self._mock_db(existing_names=all_preset_names)
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

    def test_deprecated_catalogue_composable_is_removed_and_catalogue_reseeded(self):
        """Old shipped variant 'Catalogue (composable)' should be retired on
        normal seed runs so users don't keep executing stale graphs (#720)."""
        from fichero.models import Workflow

        db = MagicMock()
        legacy = Workflow(name="Catalogue (composable)")
        legacy.is_template = True
        db.all.return_value = [legacy]
        db.save = MagicMock()
        db.delete = MagicMock()

        seeded = seed_default_workflows(db)

        deleted_names = [call.args[0].name for call in db.delete.call_args_list]
        saved_names = [call.args[0].name for call in db.save.call_args_list]
        assert "Catalogue (composable)" in deleted_names
        assert "Catalogue" in saved_names
        assert seeded == len(saved_names)

    def test_removed_legacy_catalogue_stage_presets_are_pruned_on_normal_seed(self):
        from fichero.models import Workflow

        db = MagicMock()
        legacy_names = [
            "Catalogue Full Pipeline",
            "Catalogue Each",
            "Catalogue Stage 1 - Transcribe Pages",
            "Catalogue Stage 2 - Extract Entities + KG",
            "Catalogue Stage 3 - Catalogue Artifacts",
        ]
        legacy = []
        for name in legacy_names:
            workflow = Workflow(name=name)
            workflow.is_template = True
            legacy.append(workflow)
        db.all.return_value = legacy
        db.save = MagicMock()
        db.delete = MagicMock()

        seed_default_workflows(db)

        deleted_names = [call.args[0].name for call in db.delete.call_args_list]
        assert set(legacy_names).issubset(set(deleted_names))

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


class TestTranscriptionPresetConvention:
    """Contract tests for the vision_mode / language / description convention
    across all shipped transcription presets (#2252).

    Convention:
      - Every draft `transcribe` node must set vision_mode="auto" and
        language="auto" so the user's configured vision backend (Apple Vision
        or LLM) is used, and the model detects the document language.
      - `transcribe_review` nodes always use vision_mode="llm" (structured
        LLM reasoning required for review) — exempt from this check.
      - Documented exceptions (see EXCEPTIONS below) may deviate for a
        specific technical reason stated in the JSON description.
      - Every preset description must start with "Use this when:" to help
        users pick the right preset.
    """

    # (preset_name, node_id) pairs that are intentional exceptions to the
    # vision_mode="auto" / language="auto" convention, with their reason.
    EXCEPTIONS: dict[tuple[str, str], str] = {
        # Archaic scripts (cortesana, procesal, visigótica, etc.) use letterforms
        # that Apple Vision cannot decode. LLM vision is required for the draft pass.
        ("Transcribe Paleography", "transcribe"): "archaic scripts require LLM vision",
        # Spanish Script child: vision tier aliases ($vision_small/$vision_medium/
        # $vision_large) already select the model explicitly; language="es" narrows
        # the model's orthography conventions to 19th-20th C. Spanish notarial script.
        (
            "Spanish Script v2 Child Passes (19th-20th C.)",
            "transcribe-draft",
        ): "language-specific ES preset with explicit tier aliases",
    }

    def _all_preset_dicts(self) -> list[dict]:
        return _load_preset_files()

    def test_all_transcription_preset_descriptions_start_with_use_this_when(self):
        """Presets in /Transcribe that are primarily transcription presets (i.e.
        contain a transcribe or transcribe_review node) must start their
        description with 'Use this when' so users can pick the right preset.
        Non-transcription utility presets in /Transcribe (e.g. Prepare Images
        for OCR) and presets in other folders that incidentally contain a
        transcribe node (Catalogue, Translate, etc.) are exempt."""
        bad = []
        for preset in self._all_preset_dicts():
            if not preset.get("folder_path", "").startswith("/Transcribe"):
                continue
            has_transcribe_node = any(
                n.get("tool") in ("transcribe", "transcribe_review")
                for n in preset.get("nodes", [])
            )
            if not has_transcribe_node:
                continue
            desc = preset.get("description", "")
            if not desc.startswith("Use this when"):
                bad.append((preset["name"], repr(desc[:60])))
        assert not bad, (
            "Transcription presets in /Transcribe must have descriptions starting "
            f"with 'Use this when'. Violations: {bad}"
        )

    def test_draft_transcribe_nodes_use_auto_vision_mode_and_language(self):
        """All draft `transcribe` (not `transcribe_review`) nodes must set
        vision_mode='auto' and language='auto', unless listed in EXCEPTIONS."""
        violations = []
        for preset in self._all_preset_dicts():
            preset_name = preset["name"]
            for node in preset.get("nodes", []):
                if node.get("tool") != "transcribe":
                    continue
                node_id = node.get("id", "")
                cfg = node.get("config", {})
                vm = cfg.get("vision_mode")
                lang = cfg.get("language")

                # vision_mode is optional (defaults to "auto" at runtime), but
                # when it IS set it must be "auto" unless excepted.
                key = (preset_name, node_id)
                if key in self.EXCEPTIONS:
                    continue

                if vm is not None and vm != "auto":
                    violations.append(
                        f"{preset_name}[{node_id}]: vision_mode={vm!r} "
                        f"(expected 'auto'; add to EXCEPTIONS if intentional)"
                    )
                if lang is not None and lang != "auto":
                    violations.append(
                        f"{preset_name}[{node_id}]: language={lang!r} "
                        f"(expected 'auto'; add to EXCEPTIONS if intentional)"
                    )

        assert not violations, (
            "Draft transcribe nodes must use vision_mode='auto' and "
            "language='auto'. Violations:\n" + "\n".join(violations)
        )

    def test_exceptions_are_still_present_in_shipped_presets(self):
        """Guard: if an exception entry is removed from the JSON presets the
        allowlist becomes stale.  Fail so the entry is cleaned up."""
        all_nodes_by_key: set[tuple[str, str]] = set()
        for preset in self._all_preset_dicts():
            preset_name = preset["name"]
            for node in preset.get("nodes", []):
                if node.get("tool") == "transcribe":
                    all_nodes_by_key.add((preset_name, node.get("id", "")))

        stale = [k for k in self.EXCEPTIONS if k not in all_nodes_by_key]
        assert not stale, (
            "These EXCEPTIONS entries no longer match any shipped transcribe "
            f"node — remove them from TestTranscriptionPresetConvention.EXCEPTIONS: "
            f"{stale}"
        )

    def test_every_transcribe_node_receives_source_documents(self):
        """Permanent per-page guard (#2523).

        EVERY shipped `transcribe` / `transcribe_review` node must receive the
        source's per-page `documents` so each PAGE is transcribed onto its own
        per-page artifact instead of the whole parent PDF. The files source
        emits a per-page, index-aligned (files, documents) pair; the transcribe
        tool reads `inputs["documents"]` to anchor each transcription to the
        right page document. Without that wiring the workflow silently OCRs the
        parent PDF and the per-page fix is lost.

        Two equivalent wiring mechanisms are accepted, matching how each preset
        already routes its `files`:
          (a) a graph EDGE into the node's `documents` input port
              (source_port/target_port == "documents"), used by the gold-
              standard HTR/Paleography/cloud/manuscript/typescript presets and
              the catalogue/clean-up/translate family; or
          (b) a static INPUT mapping `inputs["documents"]` resolving a source's
              documents output, used by the routed Auto-Detect preset and the
              Spanish Script sub-workflow child (which pull files the same way).

        If you add a new transcription preset, wire its documents port the same
        way you wire files — this test fails until you do.
        """
        missing: list[str] = []
        for preset in self._all_preset_dicts():
            edges = preset.get("edges", [])
            for node in preset.get("nodes", []):
                if node.get("tool") not in ("transcribe", "transcribe_review"):
                    continue
                node_id = node.get("id", "")
                has_edge = any(
                    e.get("target") == node_id
                    and e.get("target_port") == "documents"
                    for e in edges
                )
                has_input = "documents" in (node.get("inputs") or {})
                if not (has_edge or has_input):
                    missing.append(f"{preset['name']}[{node_id}]")
        assert not missing, (
            "These transcribe/transcribe_review nodes do not receive the "
            "source `documents` port, so they will transcribe the parent PDF "
            "instead of each page (#2523). Wire documents into each (an edge "
            "into the documents port, or inputs['documents']):\n"
            + "\n".join(missing)
        )

    def test_spanish_script_child_forwards_documents_contract(self):
        """The Spanish Script sub-workflow must carry `documents` across the
        sub-workflow boundary (#2523): the child declares a `documents` input
        contract and forwards it to every pass, and the parent declares the
        matching contract entry plus the files-source → sub_workflow documents
        edge. Without all four, per-page documents never reach the child and
        the sub-workflow transcribes the parent PDF."""
        presets = {p["name"]: p for p in self._all_preset_dicts()}

        child = presets["Spanish Script v2 Child Passes (19th-20th C.)"]
        child_contract_ids = {
            entry["id"] for entry in child["config"]["input_contract"]
        }
        assert "documents" in child_contract_ids, (
            "child must declare a `documents` input contract"
        )
        for node in child["nodes"]:
            if node.get("tool") in ("transcribe", "transcribe_review"):
                assert (
                    node.get("inputs", {}).get("documents")
                    == "$.inputs.documents"
                ), f"child node {node['id']} must forward documents"

        parent = presets["Transcribe Spanish Script (19th-20th C.)"]
        sub_node = next(
            n for n in parent["nodes"] if n["tool"] == "sub_workflow"
        )
        parent_contract_ids = {
            entry["id"] for entry in sub_node["config"]["input_contract"]
        }
        assert "documents" in parent_contract_ids, (
            "parent sub_workflow node must declare a `documents` input contract"
        )
        assert any(
            e["source"] == "files-source"
            and e["target"] == sub_node["id"]
            and e["source_port"] == "documents"
            and e["target_port"] == "documents"
            for e in parent["edges"]
        ), "parent must feed files-source documents into the sub_workflow node"

    def test_transcribe_review_nodes_always_use_llm_vision_mode(self):
        """Review nodes (tool='transcribe_review') must always use
        vision_mode='llm' — structured review reasoning requires LLM."""
        violations = []
        for preset in self._all_preset_dicts():
            for node in preset.get("nodes", []):
                if node.get("tool") != "transcribe_review":
                    continue
                cfg = node.get("config", {})
                vm = cfg.get("vision_mode")
                if vm is not None and vm != "llm":
                    violations.append(
                        f"{preset['name']}[{node.get('id')}]: "
                        f"transcribe_review vision_mode={vm!r} (must be 'llm')"
                    )
        assert not violations, (
            "transcribe_review nodes must set vision_mode='llm'. "
            f"Violations: {violations}"
        )


_PRESET_NAMES = sorted(p["name"] for p in _load_preset_files())


@pytest.mark.parametrize("preset_name", _PRESET_NAMES)
def test_every_default_preset_passes_execution_gate(
    preset_name: str, monkeypatch: pytest.MonkeyPatch
):
    """Every shipped preset must clear the real /execute validation gate."""
    from fichero.models import Workflow
    from fichero.workflows.runtime import to_workflow_def

    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    for tier in ("SMALL", "MEDIUM", "LARGE"):
        monkeypatch.setenv(f"FICHERO_{tier}_PROVIDER", "apple")
        monkeypatch.setenv(f"FICHERO_{tier}_MODEL", "apple-intelligence")
        monkeypatch.setenv(f"FICHERO_VISION_{tier}_PROVIDER", "apple")
        monkeypatch.setenv(f"FICHERO_VISION_{tier}_MODEL", "apple-vision")
    monkeypatch.setattr(
        "fichero.db.app.get_app_db",
        lambda: SimpleNamespace(
            get_default_model_for_category=lambda _category: None,
            list_providers=lambda: [],
        ),
    )

    preset = {p["name"]: p for p in _load_preset_files()}[preset_name]
    workflow_def = to_workflow_def(
        Workflow(
            id=f"gate-{preset_name}",
            name=preset["name"],
            description=preset.get("description", ""),
            nodes=preset["nodes"],
            edges=preset["edges"],
            config=preset.get("config", {}),
            folder_path=preset.get("folder_path", "/"),
        )
    )

    errors = [
        *validate_workflow_connections(workflow_def),
        *validate_workflow_preflight(workflow_def),
    ]
    assert errors == [], (
        f"preset {preset_name!r} fails the /execute validation gate: {errors}"
    )


class TestGlobalOnlyDefaultWorkflows:
    """Default workflows are app-level presets that belong to the global
    library only (#4102). Seeding them per-library made the same locked
    "Default Workflows" folder appear under every library in the sidebar.
    """

    def test_only_the_global_package_is_global(self):
        from fichero.db.paths import is_global_library_package

        assert is_global_library_package("/anywhere/global.fichero")
        # Sandboxed container home has its own global.fichero — still global.
        assert is_global_library_package(
            "/Users/x/Library/Containers/app.fichero.fichero/Data/"
            "Library/Application Support/Fichero/global.fichero"
        )
        assert not is_global_library_package("/Users/x/Marshall.fichero")
        assert not is_global_library_package("/Users/x/global.fichero.bak")

    def _prune_db(self, workflows):
        db = MagicMock()
        db.all.return_value = workflows
        db.delete = MagicMock()
        db.delete_default_workflow_container_nodes = MagicMock()
        return db

    def test_prune_removes_seeded_presets_and_container(self):
        from fichero.models import Workflow
        from fichero.workflows.default_workflows import prune_default_workflows

        seeded = Workflow(name="Transcribe", is_template=True)
        db = self._prune_db([seeded])

        removed = prune_default_workflows(db)

        assert removed == 1
        assert db.delete.call_args_list[0].args[0].name == "Transcribe"
        db.delete_default_workflow_container_nodes.assert_called_once()

    def test_prune_leaves_user_workflows_alone(self):
        from fichero.models import Workflow
        from fichero.workflows.default_workflows import prune_default_workflows

        # A user's own workflow, and a user COPY that kept a preset name but
        # isn't a template — neither is ours to delete.
        mine = Workflow(name="My Pipeline", is_template=False)
        copy_of_preset = Workflow(name="Transcribe", is_template=False)
        db = self._prune_db([mine, copy_of_preset])

        assert prune_default_workflows(db) == 0
        db.delete.assert_not_called()

    def test_prune_also_retires_deprecated_preset_names(self):
        from fichero.models import Workflow
        from fichero.workflows.default_workflows import prune_default_workflows

        stale = Workflow(name="Catalogue (composable)", is_system=True)
        db = self._prune_db([stale])

        assert prune_default_workflows(db) == 1
