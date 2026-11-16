# Stale needs-spec triage (spec-writer, 2026-11-08 07:45 ADT)

Read-only: no issue closed, commented or relabelled. 72 issues from `stale-needs-spec-2026-11-08.md` (the list from line 41, plus the eleven still-labelled ones above it that no step was written for today). Method per issue: the issue and its last comments; the cited spec's mention, and whether a `#### Step` or `- Behaviours:` line in that spec's build order names it (a step = a real plan; a parenthesis in a bullet = a passing cite); the code searched by what the issue does. Four read-only Sonnet agents did the reading (18 issues each); I checked every DONE line's named file or test exists. No test was run. "Step" means the cited spec's build order.

**Tally:** DONE 6 · SUPERSEDED 5 · STILL RELEVANT 9 · NEEDS SPEC 43 · UNSURE 9.

## DONE (code already does it; the label and the issue can go)

- #5880 Five consecutive failures abort a run — `builder.py` `MAX_CONSECUTIVE_ERRORS`; `activity.run.systemic-error-rule` [OK]; `tests/unit/workflows/test_systemic_error_does_not_depend_on_page_order_2026_10_20.py`. The rule depends on batch size and error rate, not page order.
- #5867 Pages run in Finder order — `source.recipe.pages-in-finder-order` [OK]; `tests/unit/recipes/test_pages_in_finder_order_5849.py`.
- #5700 Train a reader on the person's corrections — `source.train.on-the-persons-corrections` [OK]; `tests/unit/training/test_train_on_the_persons_corrections_5700.py`, `test_adopt_past_the_noise_band_5700.py`. The adopt-past-noise-band residue is its own [PARTIAL] behaviour, not this issue.
- #5648 Correction prompt explodes on a word-level pass — `source.job.review-context-fits-the-model`; `tests/unit/api/test_a_word_pass_never_outranks_read_lines_5648.py`.
- #5110 Entity merge and split have a door — `EntitiesLibraryContent.swift` (`EntityMergeSheet`, `EntitySplitSheet` from the entity table's context menu); kg-entities-and-statements Step 2.5. No Swift test found; the first-run library row mount was not checked.
- #2342 Compact iPad/iPhone context actions — `research.touch-first-context-actions` [PARTIAL]; `LibraryView+ContextMenu.swift`; the issue's own last comment says touch chat and move exist. Residue: the compact Import-to sheet (one small issue if wanted).

## SUPERSEDED (a newer spec or issue carries it; close pointing there)

- #5672 Locate Originals — built (`Models/OriginalsStore.swift`, `Views/Library/LocateOriginals.swift`, engine `relink_originals`); the reconnect-on-error work is #6306, #6307, #6308 (engine-silent-failures.md).
- #5636 Structured data spec — `specs/source/structured-data.md` exists; its remaining [GAP]s (units and precision, vocabulary, repeating groups) live there.
- #1691 KG blame and rollback — `safety/the-record.md` says it supersedes `audit.blame-and-rollback-view` (#1691, #4636); `safety/versions-and-restore.md` holds the view.
- #1342 Centralise model downloads — carried by `settings.one-catalog-unification` (#4307, ai-settings.md); spaCy models not yet covered there.
- #1152 Model management UI — the same behaviour (#4307); the issue is `status:blocked` on design.

## STILL RELEVANT (a spec has a real step; keep, re-point the label at the step)

- #6076 Measure engine RSS on a 20-page Kraken plus cloud run — recipes-run.md Step 2.3 (`recipes-run.memory.peak-ceiling-per-model-kind`); the measured table must exist before #6212 is coded.
- #5661 Copy between machines, security-review questions — moving-between-projects.md `transfer.machine.owners-devices-send` [GAP], `transfer.machine.forget-machine` [PARTIAL] (ruled 2026-10-17); behaviours but no step heading: give them one.
- #5642 Linux server image, multi-arch — `compute/linux-server-image.md` exists; hpc-runner-acenet.md Steps 1.1–1.5 and activity Step 1.13 depend on it; only single-arch Dockerfiles today.
- #4978 Research layout, related-items pane — kg-entities-and-statements Step 1.3; review-names-and-statements Step 6.1; the pane is not built.
- #4422 Inspector attributes none by default, entities as lozenges — `inspector.attributes.entities-as-lozenges` [PARTIAL]; the empty default shipped (c83036b5c); lozenges still to build; needs a step heading.
- #4397 Workflow scope contract — workflows.md Steps 1.1 (engine, built: `workflows/validation.py` `workflow_scope`) and 4.1 (the run-menu Swift half, open).
- #4387 Empty states offer the workflow — workflows.md Step 3.5 (`workflows.folders.empty-states-suggest-a-workflow`); test not yet written.
- #2054 Owner's shared-libraries view — sharing-two-macs.md Step 4.2 cites it, but that step is Set Up's sharing controls; `sharing.owner-shared-libraries-view` [GAP] (library-sharing.md) still wants its own step.
- #2020 Entity panel aggregates descendants without provenance — kg-entities-and-statements Step 1.3 (folder lens) is where the "Found in" column attaches; `EntitiesLibraryContent.swift` has none.

### Proposed milestone groupings for the owner (STILL RELEVANT, in order)

| Order | Theme (milestone) | Issues | Spec and steps | Size |
|---|---|---|---|---|
| 1 | Engine memory at scale | #6076 | recipes-run.md 2.3 (before #6212) | S |
| 2 | Workflows: scope and empty states | #4397, #4387 | workflows.md 4.1, 3.5 | M |
| 3 | Sharing: people and machines | #2054, #5661 | sharing-two-macs.md new step beside 8.9; moving-between-projects.md new step for the two behaviours | M |
| 4 | KG lenses and the Inspector | #4978, #2020, #4422 | kg-entities-and-statements 1.3; review-names-and-statements 6.1; build-notes-inspector new step | L |
| 5 | Compute: the Linux image | #5642 | linux-server-image.md (its own build order) | M, after the ACENet rehearsal |

## NEEDS SPEC (cited only in passing or as a bare [GAP]; no step, not built)

Grouped by surface so the owner can pick which get a step and which are parked.

**Panes, toolbar and workspaces** (ui/panes-workspaces.md): #4977 split opens the complement (ruled 2026-10-04); #4974 pane heads float or are a row; #4969 workspaces replace the four pane icons (ruled, table rows [GAP]); #4881 explicit pane linking by colour chip (explore/time.md blocked on it); #4378 breadcrumb as a real path; #4374 toolbar IA groups (rename, combined control, filter and sort placement left). One milestone would do: six behaviours already written, zero steps.

**Reader** (ui/reader-view.md): #4405 click a word to its source region and Find (data half landed, interaction not); #4375 inline editing in the WebKit reader (offset-integrity design unresolved); #4355 highlight-layer precedence by visible split.

**Library views** (ui/library-view-modes.md): #4412 one input grammar every mode (only the spatial fix landed); #4398 list rows: badges, actionable errors, column choice; #4581 Clear Data for a selection (ruled "delete everything"; no code).

**KG tables and provenance** (kg/kg-tables.md, kg-interactions.md, source-model.md): #4644 drag and drop, full context menu (entity drag, JSON-LD export, claim merge left); #4643 tables at scale (Swift bulk delete landed, no server batch endpoint); #4636 provenance and version model (foundation not built); #4640 Exporter Manager and folder sync (`export.exporter-manager-continuous-sync` [GAP]); #5097 certainty and damage model (waits on an owner ruling); #5508 empty KG Inspector state (bottom bar fixed d55adc3de; the empty state still caption text).

**In-app agent** (ui/research.md, modes-to-panes.md): #2067 EPIC (its open piece is manager-with-workers [GAP]); #2069 manager-with-workers runtime (`needs-design`); #2072 agent workspace (blocked on #2069); #2887 pluggable runner; #2280 chat as a control surface (shared registry built; Siri and chat-builds-workflows left); #4413 chat is a mode, a pane and an inspector ([PROPOSED]); #4041 chat column in the content zone (a different shape from the spec's). One decision: park the cluster or give #2069 a spec.

**Models and settings** (ai/ai-settings.md, local-runtimes.md): #4307 one models list (carries #1342 and #1152; the canonical issue for the #1059/#1200/#2116 cluster); #4427 server-authoritative state (observable-data-layer.md, an umbrella principle, no live change feed).

**Maps and dates** (maps-and-georeference.md, historical-text-normalization.md): #5128 map view surface (engine `georeference.py` route exists; no Swift surface); #5127 places over time and in words (engine shape exists; no screen; needs the date model #4936); #4364 undate/EDTF for uncertain dates (EDTF allowed as an export layer; evaluation not done).

**Harness, testing and boundaries**: #5995 SwiftLint warning debt (`orch.swiftlint-warnings-drained` [GAP]; the ratchet is OK); #4645 test-environment parity guard (`testenv.parity-guardrail` [MISSING]; parent of #4784–#4788); #2888 CLI importers through the audited registry (the cited behaviour is about server routes; `import-slipbox` and `import-sergio-corpus` remain); #4217 MAS build cannot open a Dev or DMG library (cited only as the nearest open issue; #5818 and #6306/#6307 are primary).

**Export and markup**: #2267 export preview in WebKit (`export.preview-before-committing-to-a-file` [GAP]); #2038 Inspector-bottom tools placement (annotation lives in `ZoomableImagePreviewMac+Annotations.swift`).

**Compute**: #4642 distil a thinking paleography VLM (hooks landed 5e129af68; the VLM unbuilt; cited in OPEN-QUESTIONS and remote-compute only).

## UNSURE (the owner must judge; one question each)

- #6012 Which hand: print no longer asks; the Spanish and Latin hands (procesal, cortesana, humanistic) and typefaces are not built. Question: a new step for the remaining hand list, or close as enough?
- #5727 Compare in Set Up: the engine path is pinned by `test_compare_in_setup_works_5727.py`; the symptom was never recorded. Question: does Compare work for you in the current app?
- #5692 Training UI gaps: the noise band is built; cost-before-train, caps, other Macs, WER and the model link have no step. Question: keep as one issue or split?
- #5571 Discovery beyond HTRMoPo: HTR-United built (`test_htr_united_datasets_5571.py`); tessdata, PyLaia/TrOCR, Transkribus not. Question: split those out, or close?
- #5254 Claims and Entities tables rebuild every row: the revision-keyed rebuild and sort fixes look built (`ClaimsLibraryContent.swift`, `ClaimsTableView.swift`); paging and the Marshall measurement unseen. Question: is the rainbow cursor gone on Marshall?
- #5120 Three homeless areas: maps and tables have homes; the map screen is deferred. Question: close the umbrella and open one issue each for IIIF ingestion and onboarding leftovers?
- #4987 Memory budget for local runs: Kraken done (#6351); the per-model-kind ceiling and the Activity RAM display are [GAP]. Question: close and track the rest under #6212 and #5358?
- #3087 Canvas to SceneKit: Spatial2DCanvas is in `Canvas/2D/Legacy/`, flag-gated. Question: delete it, or keep the fallback the spec calls settled?
- #1385 Image-editing EPIC: Question: keep it open to track the remaining legacy-tool ports, or close it for the per-operation issues (#6363, #6384)?

## Unverified

No test was run. Steps were found by `#### Step` headings and `Behaviours:` lines, so a step naming an issue in another form could be missed. Swift was read, not compiled. Not checked: #5110's first-run row mount, #2342's compact reachability, #4640's exporter extent, #5661's five points beyond the two behaviours, and the pane issues beyond grep.
