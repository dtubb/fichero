# Build order — which milestone the harness works, top to bottom

> ONE ordered list, read by `builder milestone`, `builder queue` and the loop (spec `harness/issues-and-labels.md`): the
> harness briefs the first milestone here that still has open issues, unless a person names one. The owner orders the whole
> list, by dragging it in the console (`builder status`, Milestones), which commits this file on branch `build-order` as a
> tiny batch the loop checks and lands; the order the loop uses is the landed one. `builder triage --order` proposes
> additions at the end, as a diff, never writes it. `Parked` is not ordered: buckets and lists that are not milestones.

## In order

1. `dev-workflows` — the harness itself; runs beside the product lane, built by hand by the harness builder. Spec: harness/dev-workflows.md
2. `image-enhancement` — the one product lane tonight (Step 1.1 landed first). Spec: source/image-enhancement.md
3. `Sharing & Pairing — Dead-Simple UX` — spec APPROVED with 27 steps; rename the milestone to `sharing-two-macs` when triage runs. Spec: source/sharing-two-macs.md
4. `recipe-designer` — wide onboarding; the recipe phases R1–R5 go into its build order first. Spec: source/wide-onboarding.md
5. `recipes-run` — running things and watching them
6. `activity` — running things and watching them
7. `workflows` — running things and watching them
8. `workflow-node-config` — running things and watching them
9. `source-model` — the data model and getting material in
10. `importer` — the data model and getting material in
11. `undo-trash-rollback` — the data model and getting material in
12. `panes-workspaces` — the shell
13. `modes-to-panes` — the shell
14. `library-view-modes` — the shell
15. `sidebar-crud` — the shell
16. `menus-and-commands` — the shell
17. `preview-surface` — the shell
18. `reader-view` — the shell
19. `kg-tables` — knowledge and finding
20. `kg-readable-representation` — knowledge and finding
21. `kg-entity-inspector` — knowledge and finding
22. `kg-enrichment` — knowledge and finding
23. `search` — knowledge and finding
24. `explore` — knowledge and finding
25. `research` — knowledge and finding
26. `ai-settings` — engine and providers
27. `remote-compute` — engine and providers
28. `transport-http-uds` — engine and providers
29. `engine-startup-lifecycle` — engine and providers
30. `audited-action-layer` — engine and providers
31. `observable-data-layer` — engine and providers
32. `export-pipeline` — output
33. `historical-text-normalization` — output
34. `test-environment-contract` — testing and release
35. `ui-testing-strategy` — testing and release
36. `ui-test-harness` — testing and release
37. `release-and-versioning` — testing and release

## Parked

- `Next release` (98 issues) and `cand 16` (18) — grab-bags, not specs: triage files each issue into its spec's milestone and these close.
- `Bugs - *`, `Performance - *`, `Lint - Structural Debt - *` — ops buckets, worked by bug and priority, never as a lane.
- `UX - *`, `Engine - *`, `App - *`, `Developer - *`, `Hygiene & Structure - *`, `SwiftUI/Engine - *`, `Mac App Store — *`, `Testing Overhaul — *`, `Inspector View`, `Library View`, `Keyboard Navigation`, `Search View - *`, `Sidebar & Launch Performance` — older area buckets, not specs: worked by bug and priority (lead ruling 2026-11-02).
- `cand 14`, `Later (post-release)`, `iPhone`, `HF`, `ACENet` — not worked now (lead ruling 2026-11-02).
