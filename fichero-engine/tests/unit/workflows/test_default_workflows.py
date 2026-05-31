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

    def test_catalogue_each_preset_is_configured_for_folder_fan_out(self):
        """Catalogue Each should stay wired as the bulk fan-out preset."""
        presets = {p["name"]: p for p in _load_preset_files()}
        catalogue_each = presets["Catalogue Each"]

        assert catalogue_each.get("is_template") is True
        assert catalogue_each.get("is_system") is True
        assert catalogue_each.get("folder_path") == "/Catalogue"
        assert catalogue_each.get("config", {}).get("fan_out_enabled") is True
        assert "fan_out" in catalogue_each.get("tags", [])

        node_tools = {n["tool"] for n in catalogue_each["nodes"]}
        assert "folder" in node_tools
        assert "transcribe" in node_tools
        assert "catalogue" in node_tools

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
        assert "kg_writer" in node_tools, "Catalogue preset must include kg_writer"
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
        assert extract_all_node["config"].get("persist_kg") is False
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
        kg_writer_id = _node_id(presets["Catalogue"], "kg_writer")
        extract_id = _node_id(presets["Catalogue"], "extract_all")
        assert any(
            e["source"] == extract_id
            and e["target"] == kg_writer_id
            and e["source_port"] == "kg_payload"
            and e["target_port"] == "kg_payload"
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

    def test_ner_per_page_local_has_explicit_kg_writer(self):
        presets = {p["name"]: p for p in _load_preset_files()}
        preset = presets["NER per-page (local)"]
        node_tools = {n["tool"] for n in preset["nodes"]}
        assert "kg_writer" in node_tools
        extract_all_node = next(
            n for n in preset["nodes"] if n["tool"] == "extract_all"
        )
        assert extract_all_node["config"].get("persist_kg") is False
        extract_id = _node_id(preset, "extract_all")
        kg_writer_id = _node_id(preset, "kg_writer")
        assert any(
            e["source"] == extract_id
            and e["target"] == kg_writer_id
            and e["source_port"] == "kg_payload"
            and e["target_port"] == "kg_payload"
            for e in preset["edges"]
        )

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

    def test_spanish_paleography_extract_uses_dollar_large(self):
        """Paleography baseline preset is transcription-first only."""
        presets = {p["name"]: p for p in _load_preset_files()}
        paleography = presets["Spanish Paleography (18th–19th C.)"]
        extract_nodes = [n for n in paleography["nodes"] if n["tool"] == "extract_all"]
        assert not extract_nodes

    def test_spanish_paleography_wires_extract_from_transcribe(self):
        """Spanish paleography baseline keeps transcribe-only wiring."""
        presets = {p["name"]: p for p in _load_preset_files()}
        paleography = presets["Spanish Paleography (18th–19th C.)"]
        node_tools = {n["tool"] for n in paleography["nodes"]}
        assert "transcribe_review" not in node_tools
        assert "extract_all" not in node_tools
        transcribe_node = next(n for n in paleography["nodes"] if n["tool"] == "transcribe")
        assert "provider_name" not in transcribe_node.get("config", {}), (
            "paleography transcribe must use vision defaults (no hard-coded "
            "provider alias) so Settings controls model selection"
        )

    def test_spanish_paleography_files_to_transcribe_uses_documents_port(self):
        presets = {p["name"]: p for p in _load_preset_files()}
        paleography = presets["Spanish Paleography (18th–19th C.)"]
        edges = paleography["edges"]
        file_edge = next(e for e in edges if e["id"] == "edge-files-transcribe")
        assert file_edge["source_port"] == "files"
        assert file_edge["target_port"] == "files"

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
        assert set(rmap.keys()) == {"typescript", "manuscript", "htr", "paleography"}

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
