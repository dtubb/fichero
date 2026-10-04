# Open Questions Digest

**This file is generated.** It collects each spec's own "Open questions" section (or
equivalent) verbatim, grouped by area subfolder, as a checklist for the design lead to
answer. The source of truth is always the spec itself — edit the open-questions section
there, not here, and regenerate this digest afterward.

Specs with no "Open questions" heading (their questions were already resolved as part of
approval) are listed with "None outstanding" and no checklist.

---

## docs/

### docs-citations-bibliography.md

All four answered 2026-10-04 (see spec "Rulings"):
- [x] Citation syntax = **Pandoc `[@key]`** (maintainer).
- [x] Unused `.bib` entries are **flagged too** (design lead).
- [x] Code-dependency credits = **a separate generated file**; `.bib` is for scholarship (design lead).
- [x] **Docs first**; the app surface follows from the export (design lead).

---

## harness/

### dev-orchestration-harness.md

- [x] Area leads are **on demand** (answered 2026-10-04, design lead).
- [x] fabel is **reserved for visible Xcode UI iteration** (answered 2026-10-04, design lead).
- [x] Agents/skills audit: **yes, as a separate short task** (answered 2026-10-04, design lead).

### git-worktree-workflow.md

- [x] The canonical checkout stays a **clean `main` mirror** + venv host (answered 2026-10-04,
      design lead).
- [x] Is `integration` a permanent branch? **Yes — permanent long-lived staging branch** (resolved
      2026-09-12).
- [x] **Yes** to a guardrail flagging an `ahead:0`, abandoned lane worktree, owed as a [GAP]
      (answered 2026-10-04, design lead).

---

## kg/

### archival-data-model-plan.md

_(The spec lives at `source/archival-data-model-plan.md`.)_

- [x] **Profile detection** — detected from the page and recipe, shown, editable; a change can
      cascade to the folder (maintainer, 2026-10-04).
- [x] **Where representations physically live** — both: file payload + metadata row (design
      lead, 2026-10-04).
- [x] **Is Transcription first-class now** — yes: text lives as readings on segments, in passes
      (source-model rulings 2026-09-20).
- [x] **Store responsibility** — DuckDB is the record; LanceDB and the graph are derived and
      rebuilt from it (design lead, 2026-10-04).
- [x] **New milestones?** — one milestone for the source-model set (source-model rulings 2026-09-19 item 21). Was: "Segments & Anchors" and/or "Provenance, Versions & Credit", or
      keep everything under the existing surface milestones? (Decomposition on #4639.)
- [x] **P0 export target** — answered by what is built: ALTO and PAGE XML both export today.

### kg-enrichment.md

Both answered by the maintainer 2026-10-04 (see spec "Rulings + open questions"):
- [x] Validation = **expand/compact always; SHACL where a shape is declared**.
- [x] JSON-LD import gets its own **"imported from <file>"** provenance, separate from live
      Wikidata enrichment.

### kg-entity-inspector.md

None outstanding (no "Open questions" section in the spec).

### kg-interactions.md

- [x] Comments = **their own threaded record**, anchored to any node, never a claim (maintainer,
      2026-10-04).
- [x] Drag payload = **both**: internal id in the app, JSON-LD outward (design lead, 2026-10-04).
- [ ] Which extra claim fields become table COLUMNS vs inspector-only (columns cost width)?

### kg-readable-representation.md

All four resolved 2026-09-12 (see spec "Rulings"):
- [x] Default ordering = **chronological, changeable**; source + date always shown/clickable.
- [x] Confidence = **hedge words + triangulation** (corroboration count, contradictions, linked
      sources) — "not magic"; a bare dot/number can mislead.
- [x] Connective prose = the entity's dominant claim language; claims always render in their own.
- [x] Languages = **generic, no hardcoded list**; active language(s) chosen at onboarding, per
      project (settable per collection); each language is a data table, Spanish seeded.

### kg-tables.md

None outstanding (no "Open questions" section in the spec).

### segment-representations.md

_(The spec lives at `source/segment-representations.md`.)_ All three answered 2026-10-04:
- [x] Representations = **file payload + metadata row** (design lead).
- [x] `Transcription` is first-class already: **text lives as readings on segments**, in passes (source-model rulings 2026-09-20).
- [x] Export target: **ALTO and PAGE XML both export today** (answered by what is built).

---

## testing/

### test-environment-contract.md

- [x] One shared engine env base file; the harness layers only allowlisted overrides (design
      lead, 2026-10-04).
- [x] Release always runs the full UI suite, beta on release branches, dev a smoke run on every
      push (design lead, 2026-10-04).
- [x] Model cache: tests use the developer's cached model offline and skip with a reason when
      it is missing (#5188; by the existing design, 2026-10-04).

### ui-test-harness.md

All four original questions resolved by the rulings in the spec. Remaining unknown:

- [ ] The exact app-side reason the seeded library isn't current at window-resolve time —
      pinned by one instrumented MCP run before the fix, per systematic-debugging.

### xcode-build-configs.md

- [x] `config.no-stale-sandbox-comments`: **assert the settings and delete the stale comments**;
      comment-checking only if drift recurs (answered 2026-10-04, design lead).

---

## transport/

### transport-http-uds.md

- [x] `transport.event-delivery` (#4486): **re-verify #4511 once, then write the test** (design
      lead, 2026-10-04).

---

## ui/

### sidebar-crud.md

None outstanding (no "Open questions" section in the spec).

### workflow-node-config.md

None outstanding (no "Open questions" section in the spec).

---

## Design-lead leans applied 2026-10-04 (specs not itemised above)

Each was answered in place in its spec, marked "**Answered** (design lead 2026-10-04, applying
the spec's lean)". Questions in these specs not listed here stay open in the spec.

- `ai/ai-settings.md` — runtime-state work ships before the catalog unification; per-call
  LangChain visibility goes to a backend observability milestone; older settings issues close
  once superseded, carrying distinct scope forward.
- `ai/local-runtimes.md` — MLX bundled at build time, in-process; Vision strips measured before
  any change; heavy = over 1 GB resident; FoundationModels/Vision memory counts as "system";
  runtime configurations fold into card id + step settings; build order as recommended.
- `compute/remote-compute.md` — Fichero-made Keychain key after a trial; one engine per kind of
  work; Docker Desktop after a trial; `fichero_hpc_*` renamed with no alias; Kraken in-engine not
  now; Apple adapters left out.
- `compute/jobs-and-fine-tuning.md` — one engine per kind of work; 50 sources per shard;
  publishing moves to exporter/model-card specs once owners agree; #4642 stays its own issue.
- `compute/linux-server-image.md` — third image decided from measured sizes; CUDA runtime base
  matching PyTorch's wheels.
- `compute/targets-and-connection.md` — sandboxed SSH trial first; compute-node SSH and login-node
  Apptainer fetch tried once per cluster; never installs Docker or Tailscale; three-hour sessions.
- `compute/transfer-and-results.md` — an agent can never say yes to egress.
- `explore/time.md` — storylines and arcs: HTML first, decided by measured memory cost.
- `harness/audited-action-layer.md` — OpenAPI before/after diff test later; CLI/MCP-vs-registry
  guardrail; understand the merge audit's reversal ids first; the older mutation undo retires.
- `harness/observable-data-layer.md` — engine adds item ids (`observable.change-events-carry-item-ids`,
  #4824); fix the refresh loop directly; architecture doc stays separate.
- `harness/spec-pipeline.md` — the daily check goes strict on orphan issues once worked down.
- `importer/importer.md` — capture folds in as an entry point; pluggable importers get a section
  once worked; the 100k claim needs a load profile first.
- `kg/hermeneutic-layer.md` — wire the create form's claim/passage link now; claim type belongs in
  the claim-editing spec.
- `safety/the-record.md`, `safety/undo.md` — older records stop being written and their undo
  retires; redo of a create keeps the id.
- `source/build-notes-formats-harness.md` — write PAGE XML 2019-07-15, read both.
- `source/checking.md` — statement/entity corrections in a later slice.
- `source/editable-reader.md` — typing never waits; a line saves within 300 ms, measured first.
- `source/historical-text-normalization.md` — one shared fold (`histnorm.one-shared-fold`, #3320);
  #3323 and #3326 merge; EDTF layered over existing date storage.
- `source/image-preparation.md` — YOLO trained in PyTorch, run in Core ML.
- `source/maps-and-georeference.md` — DuckDB Spatial, bundled, subject to size.
- `source/segments-and-geometry.md` — character stretch = anchor text-position form; one call per
  model (`source.tool.each-model-gets-its-own-call`, #5026).
- `source/synced-folder.md` — same quiet period as Activity.
- `ui/about.md` — copyright single-sourced (`about.copyright-single-sourced`, #3234); create the
  `about` milestone.
- `ui/activity-and-automatic-work.md` — yield to typing on the local-ML lane only; LangGraph keeps
  graph, fan-out, state and interrupt.
- `ui/automation.md` — background priority for scheduled runs, normal for "run now"; same audited
  layer.
- `ui/menus-and-commands.md` — worst offenders first; shared components with the pane as context.
- `ui/reader-overlay-frame-identity.md` — audit all three ops; stamp on rendition rows, backfill at
  open; check real libraries before inverting.
- `ui/reading-markup-annotations.md` — several tags with AND/OR, no fixed vocabulary.
- `ui/research.md` — file the engine issue before UI.
- `ui/workflows.md`, `ui/workflow-node-config.md` — node config stays separate; #252 becomes
  `workflows`; edge legality before the move; presets issue filed (#4738); #4396 re-check stands;
  typed steps after tracing duplicates and fixing `kraken_model` drift.

Answered by the existing design (2026-10-04): the importer's curation guard runs inside the one
KG writer, no separate pass; a tool gets only the working pass's reading and the maker tag is
built; spec-pipeline rule (g) keeps baseline + reasoned allowlist; test embeddings use the
developer's cached model offline (#5188).
