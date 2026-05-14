# STATE.md — Fichero

## Next Session — Start Here

**Latest commit: `7ef16274`. Branch: 0.0.2.** Backend pipeline-trust cluster sweep — 6 fixes shipped (committed + pushed, pytest-green, **NOT yet verified by a real-app run**). Process change this session: build/lint/test runs offloaded to `test-runner` subagents so the lead's context stays clear; see `docs/agent-workflow/parallel-execution.md`.

### Shipped this session (pushed to 0.0.2, subagent-verified, pending on-device check)

- **#1061** `f14346b9` — parallel-execution process docs (when to use single session / subagents / agent teams + QA review gate).
- **#1060 + #1037** `d17b5fb8` — `extract_all` fails-fast on systemic errors (`_classify_systemic_error`); per-LLM-call timing instrumentation.
- **#1029** `10939bc1` + `0efb995b` — generic quality gate (`output_quality.py` + builder check + `quality_gate` in `BASE_CONFIG_SCHEMA`). Stops the run only when **all** pages are garbage; some-garbage continues.
- **#1051** `5b0d1362` — keyword extractor salience bar (5-8 most salient) + `_KeywordsResult` runaway cap.
- **#1033** `7ef16274` — transcribe re-OCR'd born-digital PDFs in LLM vision mode; `_try_pdf_text_layer` hoisted out of the apple-only branch + `force_ocr` override.

### What to do first

1. **Verify the pushed backend work** — none of this session's commits (nor the prior session's #1000 Phase 1/2) is confirmed by a real run. Build + run a real catalogue workflow on a born-digital PDF: confirm transcribe uses the text layer (#1033), the quality gate stops an all-garbage run (#1029), and `extract_all` timing logs appear (#1037).
2. **#1054 needs Daniel's input** — the `min_score` threshold already exists and works (`db.py:664`); the marginal 42-50% results are above the 0.3 default. It's a tuning decision (what floor?) + possible UX work, not a bug. See the analysis comment on the issue.
3. **Remaining backend cluster** — #1027 (Apple decode → paid fallback), #1025 (local mermaid rendering). #1027 is tightly coupled to #1057 (`$large`=None).

### Other open 0.0.2 work

- Swift UI cluster (#1041/#1044/#1055, #1046/#1053, #1058/#1059, #1048/#1050, #1034-#1036, #1042/#1049) — needs an Xcode session for the 3-leg check. The `quality_gate` toggle (#1029) should be eyeballed in the node editor here.
- #1057 model-defaults — backend + Swift; the systemic error #1060 now aborts on, so worth pairing.
- #1056 — Stop button for workflow runs (cleanly implementable on the #1000 worker-thread seam).
- #1043 — dependency/langchain update sweep, deferred post-0.0.2.

### Don't break

- `db_manager` is per-`(path, thread)`; workflow execution runs on a worker thread; `DBWriter` exists. Read `agent-work/proposals/2026-05-14-workflow-execution-architecture.md` before touching workflow execution or the DB write path.
- `extract_all._classify_systemic_error` (#1060), `output_quality.py` + builder quality gate (#1029), `_try_pdf_text_layer` is now hoisted above the vision-mode branch in `process_vision` (#1033) — all new this session.
- `builder._execute_node` converts any tool's `result["error"]` into a `SystemicErrorDetected` abort, and now also gates on garbage output (#1029). Tools surfacing partial success must NOT set `error`.
- `StructuredDecodeError` IS an `AppleUnavailableError` subclass by design (#949/#962) — don't revert.
