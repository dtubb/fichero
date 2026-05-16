# Backend Worker Status

## Queue (Round 1 — complete)
- [x] #1001 — permissive_guardrails for extractors (DONE, committed 04a14ba4)
- [x] #1025 — drop mermaid.ink remote dependency (DONE, committed 501a4958)
- [x] #1017 — extractor schema round-trip tests (DONE, committed 345f9690)
- [x] #988  — entity resolution probabilistic scoring (DONE, committed 51929ba2)
- SKIP #1075 — breaking API change, defer to 0.0.3

## Queue (Round 2 — ALL COMPLETE ✓)
- [x] #1037 — extract_all slow on 15-page PDF (DONE, already fixed in d17b5fb8)
- [x] #1033 — transcribe re-OCRs digital PDFs with text layer (DONE, already fixed in 7ef16274)
- [x] #1030 — KG entity rows show raw repr instead of readable context (DONE, already fixed in 79d01166)
- [x] #1029 — no quality gate on garbage workflow output (DONE, quality gate + output_quality.py implemented)
- [x] #1027 — Apple Intelligence StructuredDecodeError forces fallback (DONE, on-device retry implemented)
- [x] #1020 — collapse catalogue.json + catalogue_mixed.json into one workflow (DONE)
- SKIP #1075 — breaking API change, defer to 0.0.3
- SKIP #1044 — SwiftUI only, skip

## Queue (Round 3 — Post-session bug fixes)
- [x] #1136 — CLI entity_neighborhood wrong path (DONE, committed cebf5efd, tests pass)
- [x] #1137 — CLI entity documents renders '(item)' instead of name (DONE, committed d2f4ebde)
- [ ] #1138 — Embeddings: fastembed pooling strategy changed (next)

## Status: ROUND 3 IN PROGRESS
Round 2 complete. Round 3 fixes discovered during testing: #1136 closed, #1137-#1138 pending.

## Attempts
{}

## Last Completed
#988

## IMPORTANT: Check before fixing
Many of these may already be fixed. For each issue:
1. grep the relevant source for the fix (e.g. grep for the function/error mentioned)
2. check if tests already cover the scenario
3. If already fixed: close with gh issue close N --comment "Already fixed in <commit hash>" and mark [x]
4. If not fixed: implement, run tests, commit, close
