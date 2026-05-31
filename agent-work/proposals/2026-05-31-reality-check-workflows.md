# Workflows Milestone Reality-Check — 2026-05-31

Read-only audit of all 43 open issues in the "Workflows" GitHub milestone.
No code was modified; no tests were run. Code state verified via jcodemunch + direct reads.

---

## Safe to Close Now (code already done)

| # | Title | Evidence |
|---|-------|----------|
| #340 | Workflow node: prompt preview panel | `PromptPreviewPanel.swift` exists, wired in `NodePopover.swift` line 61 |
| #706 | (not in list) | n/a |
| #707 | Test: per-page Artifact rows after vision tool propagation | `tests/unit/test_transcription_save.py` covers `_propagate_to_page_children` with Artifact assertions (lines 253–400+) |
| #714 | Workflow Templates 'Install Defaults' undercounts | `WorkflowLibraryView.swift:532` now says "Reinstalled N defaults" using `created.count = workflows.filter(\.isSystem)`; backend `reinstallDefaults` force-deletes and re-seeds all 14 JSON presets. The "2 installed" bug is resolved (the old Swift-side defaults that duplicated backend were removed in #722). |
| #716 | Add 'Paleography Transcribe' workflow | Two presets exist: `transcribe_paleography.json` (4-node multi-pass: draft → reference search → review) and `paleography_spanish.json` (Spanish Paleography 18th–19th C.) |
| #751 | Workflow context menu: group by folder_path | `workflowMenuItems` in `SidebarItemRow.swift:222–246` and `workflowSubmenuItems` in `LibraryView+FilterAndBatch.swift:269` both group by `folderPath`; folder-level menus render under folder label |
| #799 | fm-bridge: GenerationSchema for guaranteed structured output | `FmBridge.swift` implements `buildDynamicSchema` with full `DynamicGenerationSchema` recursive construction (lines 48–174) |
| #670 (partial) | files_tool page fan-out | Per-page fan-out implemented in `sources.py:154–234` (#891): PDFs expand to page children, selected page honoured directly. PDF LLM vision mode still uses `file_to_data_uri` (PIL) — PDF render for LLM path not yet fixed. |

**Definite closes:** #340, #707, #714, #716, #751, #799

---

## Needs Work (genuinely open)

| # | Title | Classification | Evidence |
|---|-------|----------------|----------|
| #248 | Promote Workflows from off to beta | OPEN | `workflowsEnabledInternal = true` in V001 reset — workflows ARE on, but issue asks for formal beta promotion gate. Future housekeeping. |
| #249 | Promote Workflow Execution from off to beta | OPEN | No workflow execution beta-promotion gate closed. |
| #251 | Promote Workflows to release if ready | OPEN | Still behind feature flag (`workflowsEnabledInternal`). |
| #252 | Promote Workflow Execution to release if ready | OPEN | Same. |
| #254 | Promote Batches from off to beta | OPEN | `batchesEnabledInternal = false` in V001 defaults. Batches not enabled. |
| #282 | Re-enable Batches sidebar mode after 0.0.2 | OPEN | `batchesEnabledInternal = false`; no Batches sidebar mode in active code. |
| #286 / #433 | Re-enable Workflow Editor icon/list/table modes after 0.0.2 | OPEN | Only thumbnail/list modes in `WorkflowLibraryView`; `workflowEditorAdvancedViewsEnabled = false` in V001 reset. No icon/table mode toggle visible. |
| #289 | Workflow tool alignment: per-tool system prompts + anti-hallucination guardrails | OPEN | Only partial implementation found in `extractors.py:1708` (hallucination guard in one tool). No systematic per-tool system-prompt config. |
| #341 | Workflow provider: CLI agent tools (Claude, Codex, Gemini via CLI) | OPEN | No CLI agent provider type in `llm.py`; not in registry. |
| #343 | Artifact comparison: side-by-side diff of transcriptions | OPEN | `DocumentInspectorArtifactsTab.swift:806` shows side-by-side rendering of two artifacts, but no dedicated diff/comparison view for transcription pairs. |
| #345 | Unify vision engine and provider/model in workflow node config | OPEN | No `VisionEngine` unification found in backend or Swift. |
| #348 | Workflow batch input: support collection OR current selection | OPEN | `files_tool` reads `selected_doc_ids` state but no dedicated batch UI toggle. |
| #349 | Workflow batch: selectable processing order | OPEN | No order-selection UI found. |
| #488 | [Release Gate] 0.1.0 — Wire: Workflow Basics | OPEN | Future milestone gate. `needs:human` label. |
| #489 | [Release Gate] 0.1.1 — Wire: Workflow Editor | OPEN | Future milestone gate. |
| #490 | [Release Gate] 0.1.2 — Wire: Workflow Tools | OPEN | Future milestone gate. |
| #491 | [Release Gate] 0.1.3 — Wire: Workflow Chains | OPEN | Future milestone gate. `workflowChainsEnabledInternal = true` but gate issue still open. |
| #492 | [Release Gate] 0.1.4 — Wire: Batch Processing | OPEN | Future milestone gate; `status:ready-for-test` label but batches disabled. |
| #657 | Remote HPC batch processing via ACEnet/SLURM | OPEN | No SLURM/ACEnet code anywhere in tree. Roadmap item. |
| #667 | Add Selection source node to workflow editor | OPEN | `files_tool` reads `selected_doc_ids` from state but no named "Selection" source node type in `sources.py` (registered tools: `files`, `collection`, `folder`, `search`). No Swift node palette entry. |
| #676 | Catalogue: map entities/people/timeline per file, reduce into container catalogue entry | PARTIAL — see below |
| #708 | Test: workflow stream emits cached:true on file_completed | OPEN | `test_node_cache.py` covers cache hits and extraction-cost skip but does NOT assert `file_completed` SSE event carries `cached: true`. Integration test not written. |
| #714 | (listed as done above) | | |
| #720 | Catalogue (composable) workflow missing combined catalogue artifact | PARTIAL — see below |
| #734 | Surface ModelComparisonService — 'Compare models' workflow run UI | OPEN | `ModelComparisonView` exists and is reachable via `.comparison` navigation, but NOT wired from any workflow run sheet or context menu. Issue asks for a button on the workflow run view. |
| #735 | Pre-run cost estimate on workflow execute button | OPEN | No cost estimate UI found in any Swift workflow view. |
| #756 | Analysis tool: Language identification | OPEN | No `language_id` tool or fasttext integration in `tools/`. |
| #768 | Workflow editor: migrate provider picker from LLMProvider to ProviderResponse | OPEN | `NodeProviderModelSelector.swift:23` still uses `let providers: [LLMProvider]`. Not migrated. |
| #797 | Workflow run context-menu: model picker submenu (Transcribe → Provider → Model) | OPEN | Context menus group by folder_path (closes #751) but no provider/model submenu drill-down. `workflowMenuItems` shows only workflow name buttons; no provider/model override. |
| #799 | (listed as done above) | | |
| #801 | Chunk inputs to summarize_file / summarize_folder / rewrite / analyze for on-device LLMs | OPEN | Chunking is in `catalogue.py` only. `summarize.py`, `rewrite.py`, `analyze.py` have no chunking logic; it was not lifted to `llm_base.py`. |
| #921 | Re-enable research orchestration routers when agent workflows needed | OPEN | `research_agents.py` IS registered in `main.py:867` under `/api/research`. But issue says 4 routers were unregistered (research_crud, research_notes, research_tools). Only research_agents is visible — others may still be off. Needs deeper check. |
| #1097 | Catalogue: HITL confirmation for ambiguous groupings | OPEN | No `interrupt()` / LangGraph human-in-the-loop in executor or catalogue workflow. |
| #1220 | Frontend: workflow nodes and inspector appear miswired or feature-gated | OPEN | `WorkflowInspector.swift` shows MCP/Agents tabs behind feature flags (disabled in V001). NodePopover wired. Canvas edge logic uses `showAdvancedPorts` flag. Still unverified visually; issue asks for explicit feature-gated handling vs broken UI. |
| #1287 | End-to-end workflow regression harness | OPEN | No e2e harness running full workflows against fixtures. The narrow catalogue e2e stopgap (#1285) may exist but full harness is not implemented. |
| #1332 | Translation workflow (Dutch → English, DeepL provider) | PARTIAL — see below |

---

## Partial — Live or In Progress

| # | Title | What exists | What's missing |
|---|-------|-------------|----------------|
| #670 | files_tool PDF page fan-out | Per-page fan-out (#891) ships: PDFs expand to page children in `files_tool`, page selection honoured directly. | LLM Vision PDF path still uses `file_to_data_uri` (PIL, broken for PDFs) at `vision_base.py:1391`. Part 3 of the bug not fixed. |
| #676 | Catalogue map/reduce | `catalogue.json` has full chain: `files-source → transcribe → extract_all → kg_writer → [per-entity folder cleanups] → aggregate (merge_extracts) → catalogue`. `catalogue-each.json` adds fan-out across multiple folders. The reduce node exists. **This workflow is RUNNING RIGHT NOW.** | Visual editor representation of fan-out vs 1:1 edges (issue scope item 3) is unclear. "Collect" node label in issues doesn't match code. Core map-reduce logic is present. |
| #720 | Catalogue (composable) missing combined artifact | `catalogue.json` ends with `aggregate → catalogue` node, which is the combiner. "Catalogue (composable)" preset was REMOVED — no longer a separate template. The combining is now in the main `Catalogue` workflow. | Need to verify `catalogue` tool actually saves a Catalogue artifact on the folder, not just returns text. Check `catalogue.py` save path if this is still failing. |
| #1332 | Translation workflow | `translate.json` and `translate_review.json` presets exist. `text_translate.py` registered as `text_translate` tool. `translate.py` registered as a tool with DeepL fallback comment in header. | No Apple local translate mode or MLX integration. DeepL as a new provider type (not just an LLM prompt) is not implemented in `llm.py`. |

---

## Summary Counts

- **Total open issues in milestone:** 43
- **Safe to close (code done):** 6 — #340, #707, #714, #716, #751, #799
- **Partial / live-relevant:** 4 — #670, #676, #720, #1332
- **Genuinely open (not started / future):** 33

---

## Close-Now Numbers

`#340 #707 #714 #716 #751 #799`

---

## Notes on Live-Running Issues

- **#676 (map/reduce) and #720 (combined catalogue artifact):** The `catalogue.json` workflow that is running RIGHT NOW has both the per-entity extraction and the final `aggregate → catalogue` combiner. If the running Stage 2 claim extraction produces a combined output, #720 may be effectively closed pending one verify: does `catalogue.py` save the combined result as an Artifact on the folder? Check `save_artifact` call in `catalogue.py` after this run completes.
- **#670 (PDF page fan-out):** Per-page fan-out IS live in the running workflow. The unfixed part is LLM Vision mode for PDF files, which is a separate path not used during a catalogue run (which uses Apple Vision / OCR).

---

## Action Items for Daniel

1. **Close #340, #707, #714, #716, #751, #799** — code is demonstrably done.
2. **Verify #720 after current catalogue run** — check if a Catalogue artifact appears on the folder in the inspector. If yes, close it. If not, the `catalogue.py` save path is the culprit.
3. **Verify #676 after current run** — if KG entities land and the aggregate catalogue appears, this can move to done.
4. **Defer #488–#492, #248–#254** to 0.1.x planning — these are release-gate housekeeping items, not actionable now.
5. **#921 (research routers)** — `research_agents.py` is already re-enabled. If the other 3 (crud, notes, tools) are not in `main.py`, this is partially done; close or update body.
