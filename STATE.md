# STATE.md — Fichero

## Next Session — Start Here

**Latest commit: `4127c2ca`. Branch: 0.0.2.** An overnight autonomous loop was launched at session end (`agent-autonomous-loop.py`, 3-phase scope: backend release-blockers → SwiftUI-logic audit → SwiftUI rendering/polish). **Check its output FIRST.**

### What to do first

1. **Review what the overnight loop did** — `git log --oneline 0.0.2` since `4127c2ca`; read `agent-work/proposals/swiftui-logic-audit.md` if Phase B ran; check for `BLOCK.md` (loop stopped itself) + iteration logs noting skipped issues. The loop commits directly to `0.0.2`, gated (pytest / 3-leg check) per commit.
2. **Verify on a real run** — build + run a real catalogue workflow on a born-digital PDF. Nothing the loop (or the prior sessions) shipped is confirmed by a real-app run. Restart the dev backend first — it gets cache-polluted by Swift test runs (see MEMORY `feedback_runalltests_pollutes_dev_backend`).
3. **#1000 is the live release-blocker** — a real run hung at 80% with the backend main thread deadlocked in `__semwait_signal` (DBWriter Future/queue). #1000 Phase 1 did NOT fully fix the freeze. If the loop's Phase A fixed it, verify; if not, top priority. Diagnosis on issue #1037.

### State of the 0.0.2 milestone

- **64 open issues** — triaged into ~6 root-cause clusters (backend-freeze, re-run-not-idempotent, inspector-doesn't-show-KG, search, workflow/activity UI, viewer polish). Needs ruthless triage: move non-crash/freeze/data-loss issues to 0.0.3.
- **Shipped this session, unverified:** #1060, #1037, #1029, #1051, #1033, #1027, #1022, #1023, + docs #1061.
- **Filed this session:** #1062–#1071 (Daniel's testing pass); reconfirmed/commented #1030, #1047, #1050, #1055.
- **Needs Daniel's input:** #1054 (search threshold value), #1057 (model-defaults UI decision).

### Don't break

- `builder._execute_node` converts any tool's `result["error"]` into a `SystemicErrorDetected` abort, AND gates on garbage output (#1029, `output_quality.assess_result_quality`). Tools surfacing partial success must NOT set `error`.
- `extract_all._classify_systemic_error` (#1060); `_try_pdf_text_layer` hoisted above the vision-mode branch in `process_vision` (#1033) + `force_ocr`; `StructuredDecodeError.kind` + `RETRYABLE_KINDS` (#1027).
- `#1000` worker-thread move did **not** fully fix the freeze — the DBWriter can still deadlock the backend. Read `agent-work/proposals/2026-05-14-workflow-execution-architecture.md` + the updated `project_workflow_execution_threading` memory before touching the DB write path.
- KG/entity *logic* belongs in the backend, not SwiftUI — see `feedback_kg_logic_in_backend` memory; scope the KG cluster as backend endpoints + thin rendering.
- `StructuredDecodeError` IS an `AppleUnavailableError` subclass by design (#949/#962) — don't revert.
