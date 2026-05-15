# STATE.md — Fichero

## Next Session — Start Here

**Branch: 0.0.2.** Latest: `29c61fbd`. The `fichero-cli` worktree was merged back to `0.0.2` (PR #1073) and then *typed* against `fichero.models` so it's a real verification tool, not a JSON-guesser. Using it surfaced two real backend bugs in minutes — **the CLI is now the engine-quality-comparison loop Daniel asked for.**

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
3. **Type the remaining CLI methods** as a sidecar: `document_inspector` → `DocumentInspectorResponse`; add a new `document_knowledge_graph` method against the #1068 endpoint (`DocumentKnowledgeGraphResponse`) — Loop #1 shipped the endpoint but the CLI doesn't expose it yet; `search`, `recent_activity`. Each typed method unlocks a comparison surface.

### Parallel 0.0.2 track (no CLI/workflow dependency)

The #1072 audit identified three HIGH clusters of misplaced SwiftUI logic: **artifacts**, **workflow runs**, **model/provider capability**. Phase B shipped the canonical KG endpoint (#1068/#1069/#1047/#1050). Remaining picks that are pytest-verifiable: **#1075** (list-endpoint envelope standardization), the audit clusters' remaining backend endpoints. Swift wiring (Phase C) stays deferred per Daniel.

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

- `client.py`: `_expect_list(raw, path)` is the contract — typed list methods must raise on wrong-shape responses, never silently coerce. `list_artifacts` unwraps the `{"artifacts": [...]}` envelope locally.
- `__main__.py` `_resolve_workflow` uses attribute access on `Workflow` objects — don't revert to `.get()`/`["..."]`.
- Loop #1's invariants still hold: `builder._execute_node` aborts on garbage output / `result["error"]` (#1029/#1060); DBWriter fails loud (#1000); PDF text-layer short-circuit runs before skip-if-artifact cache (#1033/#1064); `_classify_systemic_error` (#1060); `StructuredDecodeError.kind` (#1027).
- KG/entity logic in the **backend** (see `feedback_kg_logic_in_backend` memory).
- The auth token file (`~/Library/Application Support/Fichero/.api-key`) is overwritten by every backend launch — concurrent backends starve their clients of valid auth. Documented in `agent-work/proposals/fichero-cli-smoke.md`.
