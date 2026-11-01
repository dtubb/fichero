# Build order — which milestone the harness works, top to bottom

> Read by `builder milestone` and `builder queue` (spec `harness/issues-and-labels.md`). The harness briefs only the
> first milestone here that still has open issues, unless a person passes `--milestone`. The owner edits this file;
> `builder triage --order` proposes changes as a diff, never writes it.
>
> **Status: PROPOSED 2026-11-01 — the first four lines are tonight's order; everything below "Then" is the
> manager's guess for the owner to reorder.**

## In order

1. `dev-workflows` — the harness itself; runs beside the product lane, built by hand by the harness builder. Spec: harness/dev-workflows.md
2. `image-enhancement` — the one product lane tonight (Step 1.1 landed first). Spec: source/image-enhancement.md
3. `Sharing & Pairing — Dead-Simple UX` — spec APPROVED with 27 steps; rename the milestone to `sharing-two-macs` when triage runs. Spec: source/sharing-two-macs.md
4. `recipe-designer` — wide onboarding; the recipe phases R1–R5 go into its build order first. Spec: source/wide-onboarding.md

## Then (unordered until the owner orders them)

- `recipes-run`, `activity`, `workflows`, `workflow-node-config` — running things and watching them
- `source-model`, `importer`, `undo-trash-rollback` — the data model and getting material in
- `panes-workspaces`, `modes-to-panes`, `library-view-modes`, `sidebar-crud`, `menus-and-commands`, `preview-surface`, `reader-view` — the shell
- `kg-tables`, `kg-readable-representation`, `kg-entity-inspector`, `kg-enrichment`, `search`, `explore`, `research` — knowledge and finding
- `ai-settings`, `remote-compute`, `HF`, `transport-http-uds`, `engine-startup-lifecycle`, `audited-action-layer`, `observable-data-layer` — engine and providers
- `export-pipeline`, `historical-text-normalization` — output
- `test-environment-contract`, `ui-testing-strategy`, `ui-test-harness`, `release-and-versioning` — testing and release

## Parked

- `Next release` (98 issues) and `cand 16` (18) — grab-bags, not specs: triage files each issue into its spec's milestone and these close.
- `Bugs - Testing - Lint - *`, `Performance - *`, `Lint - Structural Debt - *` — ops buckets, worked by bug and priority, never as a lane.
