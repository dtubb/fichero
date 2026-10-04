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
- [ ] **Agents/skills audit:** there are ~31 agents and ~138 skills loaded. Many overlap
      (multiple code-reviewers, multiple session-start variants, several planning skills). Worth a
      pass to cut the ones we never invoke — separate short task, listed as a follow-up below.

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
- [ ] **Store responsibility** — DuckDB (relational) vs LanceDB (vectors) vs rdflib/SPARQL
      (graph): which store owns which slot, and how they stay in sync (ties Exporter #4640)?
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
- [ ] Drag payload: JSON-LD item vs an internal id — or both (internal for in-app, JSON-LD for
      out)?
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

- [ ] Where does the shared engine `.env` base live, and does the test harness read it +
      layer the allowlisted overrides (vs. re-listing env in Swift)?
- [ ] Which tiers get a full UI run vs. a smoke run (release always; beta on release branches;
      dev every push)?
- [ ] Model cache: one committed/seeded fixture model for embeddings tests, or point tests at
      the developer's real `~/.cache` (fast but not hermetic)?

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

- [ ] `transport.event-delivery` (#4486): write the Swift change-stream test now that the
      MainActor isolation fix (#4511 class) has landed? (Tracked; not this pass.)

---

## ui/

### sidebar-crud.md

None outstanding (no "Open questions" section in the spec).

### workflow-node-config.md

None outstanding (no "Open questions" section in the spec).
