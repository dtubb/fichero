# STATE.md — Fichero

## Next Session — Start Here

**Branch: 0.0.2.** Latest: `94add97a`. The CLI test loop is **operational end-to-end**: `library create` → bulk `import --recursive` → `workflow run --wait` (now actually waits) → `search` (semantic + fulltext + hybrid all return real results in <50ms) → `kg entities/claims/search` → `artifacts get`. Run on a fresh `~/Documents/fichero-loop-test.fichero` library with 20 staged md files from `~/code/slipbox/coded` (9.4k words). Vector search confirmed real (LanceDB embeddings auto-generated at import; "gold extraction" — not in any doc — finds the mining doc at 0.910 similarity).

**One architectural fix in flight (subagent a3791449)** — `extract_all` / `extractors` / `catalogue` all gate writes on `if container and library_path:` where `_resolve_container_doc` returns None for non-folder selections. Closes #1087 + #1105 in one shared-helper change. Live verification on the loop library will prove KG entities populate after extraction.

**Bugs filed today (10 new):** #1077 dup transcription · #1078 provider/model normalisation · #1079 workflow_name unknown · #1081 LangGraph internals leak · #1082 page-2 missing artifact · #1083 LangChain deprecation warning · #1085 maps importer · #1086 vector search verification · #1087 catalogue wastes LLM call · #1088 --wait early return (FIXED) · #1080 artifacts get gap (FIXED) · #1096–#1098 catalogue case-grouping/HITL/fan-out · #1104 import loses filename · #1105 KG never persisted · #1106 search render placeholders · #1107 --type keyword vs fulltext · #1108 MCP server.

**Loop status today:** Library bootstrap ✅ · Bulk import ✅ · Doc viewing ✅ · Vector search ✅ · Fulltext search ✅ · Hybrid search ✅ · Workflow run + wait ✅ · Entity extraction (compute) ✅ · KG persistence ❌ (subagent fixing) · Catalogue artifact save ❌ (same fix) · Original filenames ❌ (#1104, separate).


### The vision (Daniel's framing)

The engine uses Apple Vision / Apple Intelligence (smaller on-device models). Claude is a frontier model. Using the typed CLI, the loop is:
1. Run real workflows on real documents (e.g. his Preface PDF).
2. Read the document directly.
3. Compare the engine's output vs the direct read.
4. File / fix gaps in the engine to close the quality difference.

Backend = logic; CLI / SwiftUI / future iPad / web = display surfaces only. Every commit gets code-review + silent-failure + security review via subagents (per Daniel 2026-05-15) — and stays good Pythonic + good SwiftUI code.

### What to do first (in order)

1. **Fix #1074 (CRITICAL — blocks all workflow testing).** `fichero workflow run Catalogue <doc>` via CLI: kickoff returns `accepted`, then completes in seconds with `selected_doc_ids: []` and `files-source: {files: [], count: 0}`. The doc_id in `inputs.files=[...]` never reaches the Files-source node. Check what payload SwiftUI's `WorkflowExecutionService.swift` actually sends to `/api/workflow-execution/execute` — that's the reference; the CLI's payload shape is wrong. Without this fix, the comparison loop can't even start.
2. **First end-to-end comparison run.** Once #1074's fixed: `fichero workflow run Catalogue <preface-pdf-id> --wait`. Pull `artifacts <id>` and `kg entities <id>`. Read the Preface PDF directly. Compare. Write findings to `agent-work/proposals/engine-quality-2026-05-15.md` and file specific bugs for each gap.
3. **CLI ↔ SwiftUI endpoint parity** (Daniel 2026-05-15): for every endpoint the SwiftUI app uses across workflows / activity / search / library / KG, the CLI must have a corresponding typed command. Audit `fichero/fichero/Services/*Generated.swift` against `fichero/cli/client.py` — every endpoint SwiftUI calls should be reachable from the CLI, typed against the same Pydantic response model the backend declares. This is the "two surfaces, one ground truth" principle: any drift between what the CLI sees and what SwiftUI sees is a bug. Type these next: `document_inspector` → `DocumentInspectorResponse`; new `document_knowledge_graph` method for the #1068 endpoint (`DocumentKnowledgeGraphResponse` — endpoint shipped, CLI doesn't expose it); `search`, `recent_activity`, KG-search/entities/claims; activity (recent + filtered); workflow execution stream / status. Each typed method unlocks a comparison surface.

### Constitution / governance docs drift (audit 2026-05-15)

`CLAUDE.md` / `.claude/CLAUDE.md` / `docs/CLAUDE.md` are current (May 14). Everything else lags this week's work — the CLI merge, "engine is logic; clients display", autonomous loops, per-commit gates, manager pattern. Priority order:

1. **README.md — HIGH.** Still references `fichero-api/` and `fichero-swiftui/` paths from before the repo split — actively misleads. Replace with `fichero-engine/` and `fichero/` throughout. Add a **Surfaces** section (SwiftUI app / `fichero` CLI / MCP server, all thin clients on the engine). Add Knowledge Graph + CLI/MCP to Features.
2. **AGENTS.md — MEDIUM.** Wrong paths in build commands. Missing: Per-Commit Gates section (pytest+ruff+code-reviewer+silent-failure-hunter+security), Manager Pattern section (delegate to subagents), Autonomous Loop section (tmux + `agent-autonomous-loop.py` + ScheduleWakeup + BLOCK.md), CLI as Verification Surface.
3. **CONSTITUTION.md — MEDIUM.** "Two codebases" framing wrong (3+ surfaces). Add Hard Constraint: *all logic in the engine; clients render only*. Refresh diagram for one-engine / many-surfaces.
4. **VISION.md — MEDIUM.** "Phase 0 Feb 2026" stale; mid-0.0.2 with workflows, KG endpoints, CLI, autonomous loops live. Add Display Surfaces subsection naming CLI/MCP/SwiftUI + iPad/web as future. Point versioning at GitHub Milestones.
5. **SOUL.md — LOW.** Rename "two codebases must stay in sync" to "engine is the only place logic lives".
6. **USER.md — LOW.** One line that Daniel drives CLI/MCP directly; "multiple surfaces, one engine" bullet.

Approach: delegate the edits to one subagent per file (or one subagent for all six) with the audit findings as the spec. Review each diff, gate as usual.

### Parallel 0.0.2 track (no CLI/workflow dependency)

The #1072 audit identified three HIGH clusters of misplaced SwiftUI logic: **artifacts**, **workflow runs**, **model/provider capability**. Phase B shipped the canonical KG endpoint (#1068/#1069/#1047/#1050). Remaining picks that are pytest-verifiable: **#1075** (list-endpoint envelope standardization), the audit clusters' remaining backend endpoints. Swift wiring (Phase C) stays deferred per Daniel.

### Manager pattern (apply to ALL future work)

Per Daniel 2026-05-15: as manager, **delegate targeted edits to subagents** rather than doing every keystroke myself — preserve context for orchestration, decisions, and review. A subagent can write/edit a focused chunk and return a diff; I review the diff (small) rather than holding the whole file (large). Use `Agent` (general-purpose) for multi-step edits, the `pr-review-toolkit` agents for reviews, `test-runner` for the gate. Only do direct edits when the change is genuinely a one-liner or needs my judgment inline.

### Per-commit gates (apply to ALL commits going forward)

- **pytest + ruff** via a `test-runner` subagent — no commit unless green.
- **`code-reviewer` subagent** on the staged diff — address findings before commit.
- **`pr-review-toolkit:silent-failure-hunter` subagent** for any change that touches error handling, fallbacks, or response parsing — catches the exact `raw or []` pattern this session almost shipped.
- For Swift changes (when those start): swiftlint + Xcode build + `RunAllTests` via the Xcode MCP, and review the SwiftUI changes as Swift code (idioms, view-state, no logic creeping in).
- Daniel asked for **security review** too — for backend changes touching auth, library-path handling, file I/O, or external network calls, add an explicit security pass (the loop's `pr-review-toolkit:code-reviewer` covers it; spawn it with a security lens).

### What was shipped this session

- Merged `fichero-cli` → `0.0.2` (PR #1073, merge commit `22c679b4`).
- Typed `list_documents`/`get_document`/`list_workflows`/`list_artifacts` against `fichero.models` with `_expect_list` guard for loud failure (`0a91ff62`).
- Caught + fixed the `/api/artifacts/document/{id}` envelope mismatch (`ea0ddeaf`).
- Fixed `_resolve_workflow` attribute access + MockClient typed fixture (`29c61fbd`).
- Filed **#1074** (Files-source kickoff drops the doc_id — critical) and **#1075** (list-endpoint envelope inconsistency).
- CLI verified end-to-end against the real `Catalogue.fichero` library: `health`/`docs list`/`workflow list`/`artifacts` all work; `workflow run` kickoff accepted but workflow runs on 0 docs (= #1074).

### Don't break

**CLI / this session:**
- `client.py`: `_expect_list(raw, path)` is the contract — typed list methods must raise on wrong-shape responses, never silently coerce. `list_artifacts` unwraps the `{"artifacts": [...]}` envelope locally.
- `__main__.py` `_resolve_workflow` uses attribute access on `Workflow` objects — don't revert to `.get()` / `["..."]`.

**Backend invariants (from loop #1, all load-bearing):**
- `builder._execute_node` converts any tool's `result["error"]` into a `SystemicErrorDetected` abort AND gates on garbage output via `output_quality.assess_result_quality` (#1029). Tools surfacing partial success must NOT set `error`.
- `extract_all._classify_systemic_error` (#1060), `DBWriter` fails loud via bounded `_drain()` (#1000), `StructuredDecodeError.kind` + `RETRYABLE_KINDS` (#1027).
- `process_vision`: PDF text-layer short-circuit runs **before** the skip-if-artifact cache check; the cache check is gated on `not pdf_layer_used` (#1064). Don't reorder.
- `document_inspector._build_knowledge_graph` *follows* `merged_into_id` to the canonical entity — does NOT skip merged entities (skipping silently drops absorbed entities' claims; that was a #1068 under-count cause). Don't revert to skipping.
- `entity_inspector._compose_entity_summary` builds `summary` as a deterministic entity-level line — must NEVER echo a claim's text/predicate (the #1050 bug).
- #1030 migration drift: `MigrationRunner.repair_kg_svo_repr_leak` recomposes `claim.text` mirroring `extractors._write_kg_rows` — entity-bearing: `"{subject} {verb} {obj}."`, date-style: `"{stem}: {verb} {obj}."`. If the forward composition ever changes, the repair must change too or they'll diverge. The "no recoverable SVO" guard exists on BOTH claim and entity helpers — polluted rows are left for manual review, NOT blanked. Don't remove the guards.
- `StructuredDecodeError` IS an `AppleUnavailableError` subclass by design (#949/#962) — don't revert.

**Architecture / process:**
- KG/entity *logic* belongs in the backend, not SwiftUI/CLI — `feedback_kg_logic_in_backend` memory + the two audit docs in `agent-work/proposals/`. The engine is logic; CLI / SwiftUI / future iPad / web are display surfaces only.
- The auth token file (`~/Library/Application Support/Fichero/.api-key`) is overwritten by every backend launch — concurrent backends starve their clients of valid auth. Documented in `agent-work/proposals/fichero-cli-smoke.md`.
