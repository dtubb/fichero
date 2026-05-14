# STATE.md — Fichero

## Next Session — Start Here

**Latest commit: `0fe95d7e`. Branch: 0.0.2.** Long interactive testing session — 7 backend fixes + #1000 Phase 1/2 shipped (committed + pushed, pytest-green ~2511, **NOT yet verified by a real-app run**), and ~21 new issues filed (#1020–#1060) from live catalogue/KG/search testing.

### What to do first

1. **Verify the pushed backend work** — none of this session's commits (#1026/#1020/#1030/#1021/#1028, #1000 Phase 1+2) is confirmed by a real run. Build + run a real workflow. Engine bundled-app needs a briefcase rebuild; the dev backend reads live source.
2. **Fix the pipeline-trust cluster** — headline finding: catalogue runs "succeed" but come back half-empty because the model config is broken. Chain: **#1057** (`$large`=None / Vision+Audio misconfigured, UI can't fix it) → no fallback → **#1027** decode failures → **#1060** (`extract_all` never fails-fast, returns "success" at 100% chunk failure) → **#1029** (no quality gate, failed pages marked "Completed"). Fix #1060 + #1029 + #1037 (NER per-chunk logging) backend-first — all pytest-verifiable. #1057's UI half needs Xcode.
3. **#1000 Phase 2 next increment** — migrate KG entity/claim writes onto `DBWriter` (`upsert_entity` is read-modify-write — block on the writer Future; `save_claim` stays async). Wants review — see the proposal.

### Other open 0.0.2 work

- ~21 new issues #1020–#1060 — theme clusters: views-don't-re-read-live-data (#1041/#1044/#1055), search (#1032/#1046/#1053/#1054), model-selection (#1057/#1058/#1059), NER-black-box (#1037/#1048), entity-description-is-one-claim (#1050). The Swift UI cluster needs an Xcode session for the 3-leg check.
- #1056 — Stop button for workflow runs (cleanly implementable on the #1000 worker-thread seam).
- #1043 — dependency/langchain update sweep, deferred post-0.0.2.

### Process (Daniel's ask — see the QA-process issue)

Daniel wants a QA-review process — frontend/backend/security review agents — and to offload build/lint/test to subagents / agent-teams so the main agent's context stays clear, possibly run as an autonomous loop. The recurring bug patterns (see MEMORY.md) slipped through because there's no review gate on direct-to-0.0.2 commits. Filed as a GitHub issue.

### Don't break

- `db_manager` is now per-`(path, thread)`; workflow execution runs on a worker thread; `DBWriter` exists. Read `agent-work/proposals/2026-05-14-workflow-execution-architecture.md` before touching workflow execution or the DB write path.
- `extractors.py` `_normalize_kwarg_repr_fields` (#1030), `documents.py` `_cascade_delete_kg_rows` (#1021), `main.py` `_install_warning_filters` (#1028) — all new this session.
- `StructuredDecodeError` IS an `AppleUnavailableError` subclass by design (#949/#962) — don't revert.
