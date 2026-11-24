# Ground truth — marked by hand, shown in the sidebar, feeding training and the bake-off — Design Spec (#4947, #5404)

> Milestone: source-model (the spec set's one milestone; the training half's issues sit in `remote-compute`)
> Manual: TBD — a "Ground truth" section: what marking a line, a page or a reading as ground truth means, where the
> marked things are listed (the Ground Truth smart folders in the sidebar), and how they are used (training, the
> bake-off, measuring a model).
>
> Design-led (Testing Constitution). **Status: DRAFT 2026-11-18** (the reviewer, from the owner's direction of 2026-11-18;
> the owner approves). Facts read from `origin/integration` d01807cd12, file and line, nothing run; the inventory is in
> `reviews/2026-11-18-runner-review-2.md` §D. A COMPANION of `source/readings-and-apparatus.md` (readings and their
> makers), `source/checking.md` (verdicts), `source/formats-and-training.md` (training sets), `compute/training-and-evaluation.md`
> (what trains and how it is scored), `ui/search.md` (smart folders) and `ui/models-and-compute-window.md` (the trained
> models' rows). This file owns ONE thing: what ground truth IS in Fichero, how a person marks it, where it shows, and the
> one rule every consumer reads.
> Tags: **[OK]** built and pinned · **[PARTIAL]** exists in part · **[GAP]** designed, not built · **[BROKEN]** built and
> contradicting the line. Every non-[OK] line cites an issue.

## Intent (the design)

A person says "this is right" once, on the thing they checked (a line's reading, a region, a whole page's pass), and
Fichero remembers it as ground truth: it is listed in the sidebar under Ground Truth, by kind (lines, regions, pages,
names, statements), so the person always knows how much truth the project holds; every training set, every bake-off
and every measurement reads the SAME rule for what counts; a model never teaches on it as if it were its own, and a
model's verdict never overrules it. Imported transcriptions (PAGE, ALTO, TEI) are not truth until a person says so.

## Prior art

- **Transkribus** and **eScriptorium**: a page or line has a "ground truth" status set by a person; training sets are
  built only from those; the count of GT pages is shown per document. We adopt the explicit mark and the per-kind count.
- **HTR-United** and the open HTR corpora: ground truth is a dataset with provenance and a licence; we keep the
  provenance (`human`, the person, the date) on the mark and export it as such (`source/formats-and-training.md`).
- **Label Studio / Prodigy**: "accepted" annotations are a filter, not a copy. The sidebar's Ground Truth folders are
  smart folders (a saved search), never a second store.

## What exists today (read 2026-11-18)

- **The rule.** `models/segments.py:666-673` `made_by_a_person`: a pass counts when `provenance_kind == "human"` or
  `SegmentPass.ground_truth` is true. The bake-off (`recipes/bakeoff.py:310-346`), the evaluation
  (`training/evaluation.py:288-312`, `checked_pass`, `trust_of`) and the person training set (`training/kraken_set.py:318`,
  teacher `PERSON`) all read it.
- **The mark.** `PUT /api/segments/passes/{pass_id}/ground-truth` → `segment.pass_ground_truth`
  (`api/routes/document/segments.py:1185-1201`, undoable): a whole PASS of a page. The app reads the flag
  (`fichero/fichero/Models/Segment.swift:315-316`) but offers no control to set it.
- **Corrections.** `POST /api/segments/{id}/correct` (`api/routes/document/segment_readings.py:992`) makes a human
  reading; `POST .../readings/choice` (`:956-960`) chooses one, a person only. A corrected or chosen line counts
  (`kraken_set.py:41-46`).
- **Verdicts.** `checking/verdicts.py:18-30`: a person's verdict outranks a model's; a model's reject leaves a line out
  of a set; a passing line gets no verdict.
- **Not truth.** Imported passes keep the file's provenance (`segments.py:1197-1199`); the markup check ✓/✓✓/✓✓✓
  (`markup.check.cycle`) is a rating, read by no training set; a teacher pick excludes `human` passes
  (`recipes/train_offers.py:207-212`).
- **Nothing lists it.** No saved search, smart folder or sidebar node filters on ground truth or provenance
  (`ui/search.md` `search.smart-folders-as-sidebar-folders` [PARTIAL] #4114; the search routes and the Swift sidebar
  builders have no such filter).

## The design

1. **One mark, three grains.** Ground truth is marked on a reading (a line: "this reading is right"), on a region or
   table segment ("this shape is right"), or on a page's pass ("every line here is right"). The line mark is the one
   people use; the page mark is a shorthand for every line of the pass; the region mark is for layout training.
   `source.reading.ground-truth-is-a-reading` ([GAP] #4947) is this line grain.
2. **One rule, one function.** `made_by_a_person` grows to the reading grain and is the ONLY rule: the bake-off, the
   evaluation, every training-set builder and the sidebar's smart folders call it. A model never writes it.
3. **Shown in the sidebar.** A Ground Truth group under the project holds one smart folder per kind: Lines, Regions,
   Pages, Names, Statements, each with its count; opening one lists the marked things (the segment list for lines and
   regions, the pages list for pages, the entity and claim tables for names and statements). They are saved searches with
   a `ground_truth` filter, built in by the engine for every project (`search.smart-folders-as-sidebar-folders`).
4. **Marking by hand, where the person is.** The Reader's and the segment editor's line verbs gain "Mark as Ground
   Truth" (and its undo, "Not Ground Truth"); the page's context menu "Mark This Page's Reading as Ground Truth"; a
   region's menu the same; a chord through the command table. Correcting a line marks it (a correction IS the person's
   word, `source.reading.correct-a-line`); choosing a reading marks it; a markup check ✓✓✓ does NOT (it stays a rating,
   unless the owner rules otherwise: open question 1).
5. **Feeding training and measuring.** A training set's "person" teacher is the ground-truth set, by kind: lines →
   Kraken reader and vision LoRA; regions → YOLO; names → the names tagger (when one exists, #5536); statements → the
   statement grammar (later). The bake-off's reference and the evaluation's held-out pages are drawn from the same set;
   a model is never measured on lines it trained on (`training.set.held-out-never-trained`). The Models and Compute
   window's Trained here rows say how much ground truth each model was trained on (`models.ground-truth.counts`).
6. **Honest counts.** A smart folder's count is the count the training offer uses ("Train on your 312 corrected lines",
   `recipes/train_offers.py`), so the person sees the same number in the sidebar and in the Train offer.

## Behaviours

- `truth.rule.one-function` — **[PARTIAL]** (#4947, #5404; built: `made_by_a_person` for a pass, read by the bake-off,
  the evaluation and the person training set; not built: the reading and region grains, the sidebar reading it) every
  consumer of "is this right" calls `made_by_a_person` (or its reading-grain sibling); a grep of the engine for a second
  rule finds none. *Test:* `fichero-server/tests/unit/recipes/test_import_ground_truth.py`,
  `fichero-server/tests/unit/training/test_train_on_the_persons_corrections_5700.py` (extend: the three grains, one rule).
- `truth.mark.on-a-reading` — **[GAP]** (#4947; `source.reading.ground-truth-is-a-reading` owns the data model) a person
  marks a reading as ground truth (`PUT /api/segments/{id}/readings/{reading_id}/ground-truth`, an undoable action with
  the person and the time), and a correction or a chosen reading is marked by that act. Ruled 2026-11-21 (owner): the
  person is anyone correcting as they work (the owner, a student, a research assistant), and what they started from does
  not matter: a model's transcription corrected by hand is a person's reading; no figure waits on a paid expert. The
  blind-hands benchmark reads this mark (`hands.truth.reference-is-a-persons-or-says-so`, `source/read-any-hand.md`).
  *Test (to write):* marking a
  reading makes the line count for the person set; a model's write never sets the flag. Not built: needs the reading-grain data model (`source.reading.ground-truth-is-a-reading`); the flag exists only on a pass (`SegmentPass.ground_truth`).
- `truth.mark.on-a-region` — **[GAP]** (#5525) a region or table segment is marked ground truth the same way; the YOLO set
  (`training/yolo_set.py` `persons_regions`) reads the mark beside provenance `human`.
- `truth.mark.on-a-page` — **[PARTIAL]** (#4947; built: `segment.pass_ground_truth`, the route and the undo; not built:
  the app's control) the page's pass mark exists and the Reader's page menu offers it.
- `truth.mark.imports-are-not-truth` — **[OK]** (#4947) an imported PAGE, ALTO or TEI pass keeps its file's provenance
  and counts as truth only once a person marks it; the bake-off names the unmarked imports
  (`recipes/bakeoff.py:324-333` `unmarked_import_pages`). *Test:* `fichero-server/tests/unit/recipes/test_import_ground_truth.py`.
- `truth.mark.never-by-a-model` — **[OK]** (#5404; `source.check.model-never-a-person` owns it) no model call, check or
  recipe step sets the mark; a model's verdict never outranks a person's (`checking/verdicts.py:18-21`). *Test:*
  `fichero-server/tests/unit/training/test_person_reject_outranks_model_confirm_6327.py`.
- `truth.sidebar.smart-folders-per-kind` — **[GAP]** (#4114; `search.smart-folders-as-sidebar-folders` owns the
  mechanism) every project has a Ground Truth group with Lines, Regions, Pages, Names and Statements smart folders, each
  badged with its count, each a saved search with the `ground_truth` filter the engine seeds; opening one lists the marked
  things in the kind's own view. *Test (to write):* a seeded project with three marked lines shows Lines (3); marking a
  fourth updates the count through the change stream. Not built: needs the sidebar smart-folder mechanism (`search.smart-folders-as-sidebar-folders`, #4114); no engine search filter `ground_truth` exists.
- `truth.sidebar.count-is-the-offers-count` — **[GAP]** (#5440) the Lines folder's count equals the number the Train
  offer names and the bake-off's "N corrected lines on M pages" (`recipes/bakeoff.py` `MIN_LINES`, `MIN_PAGES`). Not built: needs the Lines folder (`truth.sidebar.smart-folders-per-kind`); the offer's count is `bakeoff.ground_truth`.
- `truth.feeds.training-and-the-bake-off` — **[PARTIAL]** (#4947, #5894; built: the person set for Kraken, the bake-off's
  reference, the evaluation's held-out pages; not built: the bake-off's reads as training lines
  (`compute.tune.bakeoff-reads-become-training-lines` [GAP]), names and statements sets) every training set's person
  teacher and every measurement's reference are the ground-truth set of the kind, by the one rule, held-out pages never
  trained on. *Test:* `fichero-server/tests/unit/training/test_train_on_the_persons_corrections_5700.py`,
  `fichero-server/tests/unit/training/test_bakeoff_dataset_5894.py`.
- `truth.export.carries-provenance` — **[GAP]** (#4946, #4947; `source/formats-and-training.md` `source.train.ground-truth`
  owns the format) an exported training set or PAGE XML says which lines are ground truth and by whom. Not built: needs the export format decision in `source/formats-and-training.md`.

## Build order

### Stage 1 — The mark and the rule

#### Step 1.1 — Ground truth on a reading and a region; one rule for three grains (#4947)
- Behaviours: `truth.rule.one-function`, `truth.mark.on-a-reading`, `truth.mark.on-a-region`, `truth.mark.on-a-page`
- Tests: fichero-server/tests/unit/recipes/test_import_ground_truth.py (extended; the reading-grain route's test to write beside it)
- Size: M

### Stage 2 — The sidebar

#### Step 2.1 — Ground Truth smart folders per kind, with counts (#4114)
- Behaviours: `truth.sidebar.smart-folders-per-kind`, `truth.sidebar.count-is-the-offers-count`
- Tests: fichero-server/tests/unit/recipes/test_import_ground_truth.py (the counts the folders show; the seeded saved searches' test to write in fichero-server/tests/unit/api/)
- Depends on: 1.1
- Size: M

### Stage 3 — Feeding training, the bake-off and the export

#### Step 3.1 — One set feeds every trainer and measure; exports carry it (#5894, #4946)
- Behaviours: `truth.feeds.training-and-the-bake-off`, `truth.export.carries-provenance`
- Tests: fichero-server/tests/unit/training/test_train_on_the_persons_corrections_5700.py (extended), fichero-server/tests/unit/training/test_bakeoff_dataset_5894.py, fichero-server/tests/unit/remote_read/test_read_package.py
- Depends on: 1.1
- Size: M

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | the Mark as Ground Truth verbs enable on a reading, a region, a page; the folders' counts render as served | `fichero/Tests/Unit/general/Views/Sidebar/` (to write) |
| Backend (pytest) | y | one rule, three grains; imports are not truth; a model never marks; the seeded smart folders and their counts; the person set equals the marked set | the files named above |
| MCP | y | `fichero_segment_readings` carries the mark; the training set preview counts it | `fichero-mcp/tests/test_mcp_generated.py` |
| CLI | n | — | — |

## Open questions for the owner

1. **Does ✓✓✓ (the markup check's third state) mark ground truth?** Recommended: no; it stays a reading aid, and "Mark
   as Ground Truth" is its own verb, so a count in the sidebar is never a guess.
2. **Names and statements:** is a confirmed entity or an accepted claim ground truth for the tagger and the grammar, or
   only for the knowledge graph? Recommended: yes, the same mark, so #5536's names tagger has a set the day it exists.
