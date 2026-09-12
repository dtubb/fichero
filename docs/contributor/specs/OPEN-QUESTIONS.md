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

- [ ] Citation syntax in Markdown docs — Pandoc-style `[@key]`, or a plainer `{{cite:key}}`?
      (Pandoc `[@key]` is the standard and gives free rendering/export via pandoc-citeproc.)
- [ ] Should the guardrail also flag UNUSED `.bib` entries (dead references), or only orphans?
- [ ] Do code-dependency credits live in the same `.bib` (as `@software` entries) or a separate
      generated file? (Lean: separate generated file from manifests; `.bib` is for scholarship.)
- [ ] Is the app's "where this comes from" surface in scope now, or docs-only first? (Lean: docs
      first; the export makes the app surface cheap later.)

---

## harness/

### dev-orchestration-harness.md

- [ ] Is a standing opus area-lead per area worth its coordination cost, or is on-demand (per big
      milestone) enough? (I lean on-demand — this session was all done flat + fast.)
- [ ] fabel's role: reserve it for visible Xcode UI iteration, or also for cheap bulk writing?
- [ ] **Agents/skills audit:** there are ~31 agents and ~138 skills loaded. Many overlap
      (multiple code-reviewers, multiple session-start variants, several planning skills). Worth a
      pass to cut the ones we never invoke — separate short task, listed as a follow-up below.

### git-worktree-workflow.md

- [ ] Should the canonical checkout (`~/code/fichero`) ever hold uncommitted work, or stay a clean
      `main` mirror + venv host only? (Lean: clean mirror — all work happens in worktrees.)
- [ ] Is `integration` a permanent branch, or created per-batch and deleted after it reaches `main`?
- [ ] Worth a guardrail asserting no lane worktree is `ahead:0` and abandoned (auto-flag rot)?

---

## kg/

### archival-data-model-plan.md

- [ ] **Profile detection** — user-picked only, or auto-detected from the page? Editable after?
- [ ] **Where representations physically live** — derivative files (like `_segment_image`), a
      table, or both (file payload + metadata row)?
- [ ] **Is Transcription first-class now** (P2) or does P0 read the existing transcription text
      and defer the multi-edition table?
- [ ] **Store responsibility** — DuckDB (relational) vs LanceDB (vectors) vs rdflib/SPARQL
      (graph): which store owns which slot, and how they stay in sync (ties Exporter #4640)?
- [ ] **New milestones?** — "Segments & Anchors" and/or "Provenance, Versions & Credit", or
      keep everything under the existing surface milestones? (Decomposition on #4639.)
- [ ] **P0 export target** — ALTO or PageXML first?

### kg-enrichment.md

_Section heading in spec is "Rulings + open questions"; ruled items are recorded there for
context, only the "Still open" items are checklist items here._

- [ ] Validation strength: JSON-LD expand/compact only, or also SHACL shapes (and who authors
      the shapes)? *(Recommend: expand/compact always; SHACL where a shape is declared.)*
- [ ] Does JSON-LD import create a separate "imported" provenance layer distinct from Wikidata-
      enrichment claims? *(Recommend: yes — import provenance = the file/source, distinct from
      live-authority enrichment.)*

### kg-entity-inspector.md

None outstanding (no "Open questions" section in the spec).

### kg-interactions.md

- [ ] Comments: a first-class `Comment` record (threaded?) or a claim of a "comment" type?
- [ ] Drag payload: JSON-LD item vs an internal id — or both (internal for in-app, JSON-LD for
      out)?
- [ ] Which extra claim fields become table COLUMNS vs inspector-only (columns cost width)?

### kg-readable-representation.md

- [ ] Default ordering for a biography — chronological, or by-source? (Both are behaviors; which is
      the default a reader lands on?)
- [ ] How should confidence read in prose — hedge words, a visible marker, or a separate section?
- [ ] Connective/structuring prose language when an entity's claims mix languages — the dominant
      claim language, or section per language? (Claims themselves always render in their own.)
- [ ] Which languages are actually in the current corpus (Spanish, plus…?) — sets which lexicon
      tables ship first.

### kg-tables.md

None outstanding (no "Open questions" section in the spec).

### segment-representations.md

- [ ] Where do representations physically live — derivative files next to the page (like the
      existing `_segment_image` derivatives), a table, or both (file payload + metadata row)?
- [ ] Is `Transcription` a first-class record now, or does slice-0 read the existing
      transcription text and defer the multi-edition table to #4638?
- [ ] Which standard is the slice-0 export target — ALTO (line/word geometry) or PageXML?

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

- [ ] `config.no-stale-sandbox-comments`: worth the parsing complexity, or is asserting the
      *settings* enough and we just delete the stale comments? (Lean: assert settings; delete
      stale comments as part of the harness fix; add comment-checking only if drift recurs.)

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
