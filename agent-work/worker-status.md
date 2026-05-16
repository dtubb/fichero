# Backend Worker Status

## Queue (Round 1 — complete)
- [x] #1001 — permissive_guardrails for extractors (DONE, committed 04a14ba4)
- [x] #1025 — drop mermaid.ink remote dependency (DONE, committed 501a4958)
- [x] #1017 — extractor schema round-trip tests (DONE, committed 345f9690)
- [x] #988  — entity resolution probabilistic scoring (DONE, committed 51929ba2)
- SKIP #1075 — breaking API change, defer to 0.0.3

## Queue (Round 2)
- [ ] #1037 — extract_all slow on 15-page PDF
- [ ] #1033 — transcribe re-OCRs digital PDFs with text layer
- [ ] #1030 — KG entity rows show raw repr instead of readable context
- [ ] #1029 — no quality gate on garbage workflow output
- [ ] #1027 — Apple Intelligence StructuredDecodeError forces fallback
- [ ] #1020 — collapse catalogue.json + catalogue_mixed.json into one workflow
- SKIP #1075 — breaking API change, defer to 0.0.3
- SKIP #1044 — SwiftUI only, skip

## Current
next: #1037

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
