# Build order — which milestone the harness works, top to bottom

> ONE ordered list, read by `builder milestone`, `builder queue` and the loop (spec `harness/issues-and-labels.md`): the
> harness briefs the first milestone here that still has open issues, unless a person names one. The owner orders the whole
> list, by dragging it in the console (`builder status`, Milestones), which commits this file on branch `build-order` as a
> tiny batch the loop checks and lands; the order the loop uses is the landed one. `builder triage --order` proposes
> additions at the end, as a diff, never writes it. `Parked` is not ordered: buckets and lists that are not milestones.

## In order

1. `Builder` — the harness itself (the milestone was `dev-workflows` in this file and `dev-orchestration-harness` on GitHub until the Phase 0 batch); runs beside the product lane. Spec: harness/building-fichero-locally.md
2. `image-enhancement` — the one product lane tonight (Step 1.1 landed first). Spec: source/image-enhancement.md
3. `Sharing & Pairing — Dead-Simple UX` — spec APPROVED with 27 steps; rename the milestone to `sharing-two-macs` when triage runs. Spec: source/sharing-two-macs.md
4. `recipe-designer` — wide onboarding; the recipe phases R1–R5 go into its build order first. Spec: source/wide-onboarding.md
5. `recipes-run` — running things and watching them: a recipe run from Start to the summary. Spec: source/recipes-run.md (how any run fails, pauses and goes on: compute/runner-reliability.md)
6. `activity` — running things and watching them: the Activity pane and window, the one job model. Spec: ui/activity-pane.md
7. `read-any-hand` — flagship, a small standing measurement lane beside Activity and the runner (owner 2026-11-21): the blind-hands benchmark, the held-out split, calibration; Stage 0 is two weeks of measurement with no product code. Spec: source/read-any-hand.md (correct, measure, distil, added 2026-11-22: the shared contract compute/correct-measure-distil.md, Steps 1.1 to 4.2, built first; then in this spec Step: 1.5 and Step: 2.6)
8. `reconstruct-the-record` — flagship, in parallel with `read-any-hand` (owner 2026-11-21): the cross-archive check set first, then the graph of people, places and events measured on it. Spec: kg/reconstruct-the-record.md (correct, measure, distil, added 2026-11-22: Step: 0.4 and Step: 2.4)
9. `people-and-lives` — exploring an archive from a person (owner 2026-11-21): the person record with links a person accepts, rejects, splits and merges; the biography page put together from fragments, every line one click from its page; the stitch bench; the life band, who names whom, the archive's shape and gaps; lives of things, nature and the spiritual with agents of any kind and a network panel of recorded ties (Stage 6); living people; private quality checks only. Stage 1 runs beside `reconstruct-the-record` Stage 0. Spec: kg/people-and-lives.md (kinds of thing and relation: kg/ontological-layer.md) (correct, measure, distil, added 2026-11-22: Step: 3.4 and Step: 5.2)
10. `concepts-and-terms` — exploring an archive from a word or an idea (owner 2026-11-21): the sources' own terms (vocabulary, concordance, the attestation sheet), counts as ranges with their denominator, the historian's concepts and concept-led search, the life of a word or a category with witchcraft and gender as worked examples (Stage 5), export for a footnote; the model proposes no concept. Stage 1 needs only text. Spec: explore/concepts-and-terms.md (the historian's layer: kg/hermeneutic-layer.md) (correct, measure, distil, added 2026-11-22: Step: 1.6 and Step: 3.7)
11. `research-operations` — the research pilot (owner 2026-11-21): the builder drives the pilot through the Fichero MCP now (Stage 0); then leads, steps, the brief, catalogue adapters and the Pi and Claude Code hook-up; runs beside the `research` milestone's UX steps. Spec: ui/research-operations.md
12. `workflows` — running things and watching them: the workflow editor and bar. Spec: ui/workflows.md
13. `workflow-node-config` — running things and watching them. Spec: ui/workflow-node-config.md
14. `source-model` — the data model and getting material in
15. `importer` — the data model and getting material in. Spec: importer/importer.md
16. `undo-trash-rollback` — the data model and getting material in
17. `panes-workspaces` — the shell
18. `modes-to-panes` — the shell
19. `library-view-modes` — the shell
20. `sidebar-crud` — the shell
21. `menus-and-commands` — the shell
22. `preview-surface` — the shell
23. `reader-view` — the shell
24. `kg-store-and-query` — knowledge and finding: one link table of names, statement ends as ids, counts in SQL, bounded walks (2026-11-20 review). Spec: kg/kg-store-and-query.md
25. `kg-confidence-and-provenance` — knowledge and finding: what a confidence means, where it came from, the extractor taught on this Mac (2026-11-20 review). Spec: kg/kg-confidence-and-provenance.md
26. `kg-rendering` — knowledge and finding: the graph drawn, inspected and read (2026-11-20 review). Spec: kg/kg-rendering.md
27. `search-correct-and-fast` — knowledge and finding: search that finds what it says and answers in time (2026-11-20 review). Spec: ui/search.md
28. `export-roundtrip` — output: what is exported comes back on import (2026-11-20 review). Spec: export/exporter.md
29. `readers-measured` — getting material in: each reader measured per script, the default chosen from the measures (2026-11-20 review). Spec: source/readers.md
30. `kg-tables` — knowledge and finding
31. `kg-readable-representation` — knowledge and finding; the buildable steps sit in the realisation spec, the rulings stay in kg/kg-readable-representation.md. Spec: kg/kg-paragraph-realisation.md
32. `kg-entity-inspector` — knowledge and finding
33. `kg-enrichment` — knowledge and finding
34. `search` — knowledge and finding
35. `explore` — knowledge and finding
36. `research` — knowledge and finding
37. `ai-settings` — engine and providers
38. `remote-compute` — engine and providers
39. `transport-http-uds` — engine and providers
40. `engine-startup-lifecycle` — engine and providers
41. `audited-action-layer` — engine and providers
42. `observable-data-layer` — engine and providers
43. `export-pipeline` — output
44. `historical-text-normalization` — output
45. `test-environment-contract` — testing and release
46. `ui-testing-strategy` — testing and release
47. `ui-test-harness` — testing and release
48. `release-and-versioning` — testing and release
49. `cloud-permission-and-spend` — caps in Settings, images to the cloud, a refusal with a way through. Spec: ai/cloud-permission-and-spend.md

## Parked

- `Next release` (98 issues) and `cand 16` (18) — grab-bags, not specs: triage files each issue into its spec's milestone and these close.
- `Bugs - *`, `Performance - *`, `Lint - Structural Debt - *` — ops buckets, worked by bug and priority, never as a lane.
- `UX - *`, `Engine - *`, `App - *`, `Developer - *`, `Hygiene & Structure - *`, `SwiftUI/Engine - *`, `Mac App Store — *`, `Testing Overhaul — *`, `Inspector View`, `Library View`, `Keyboard Navigation`, `Search View - *`, `Sidebar & Launch Performance` — older area buckets, not specs: worked by bug and priority (lead ruling 2026-11-02).
- `cand 14`, `Later (post-release)`, `iPhone`, `HF`, `ACENet` — not worked now (lead ruling 2026-11-02).
