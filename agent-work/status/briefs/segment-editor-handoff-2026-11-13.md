# Segment editor: handoff, 2026-11-13 (night)

Paste the prompt below into the next session. The report for the manager is the second half.

---

## Hand-off prompt

You are the segment-editor worker. Worktree `/Volumes/Fichero Dev Disk/code/fichero-worktrees/seg-editor`,
branch `seg-editor`, pushed to GitHub (`dtubb/fichero`) at `c55efd7bb`. Open THAT worktree's
`fichero/fichero.xcodeproj`, scheme **Fichero (Dev Local)**, destination **My Mac** (not the iPad: building for the
iPad fails with "Unable to resolve module dependency").

Read first: `docs/contributor_manual/specs/ui/segment-editor.md` (each entry now has *Built (2026-11-13)* and
*Not built* notes) and this file's report below.

Rules (unchanged): no pbxproj edits, and **never commit `fichero/fichero.xcodeproj/project.pbxproj`** (Xcode
rewrites it; its rewrite drops App Store settings and fails `check_xcode_config_invariants` and
`check_test_plans_runnable`); no new dependencies; semantic fonts; logic in the engine; every edit one audited
undoable engine action; swiftlint on your diff; engine tests with `PYTHONPATH=$PWD/fichero-server/src` and
`~/code/fichero/.venv/bin/python`, only the files you touch; the worktree's `.venv` symlink must not be committed
(`git add -A -- . ':!fichero/fichero.xcodeproj/project.pbxproj' ':!.venv'`). Push with
`git -c credential.helper='!gh auth git-credential' push https://github.com/dtubb/fichero.git seg-editor`.

Before testing in the app: **restart the engine** (tmux `f_engine`, started 17:28 on 2026-11-13, from this
worktree, scratch state `~/Fichero Dev Test/state`). The contract was re-synced tonight, so the old engine's
contract hash no longer matches the app's.

Next, in order:
1. Check in the running app what was built tonight (list below), with the owner, and fix what they find.
2. Stage 2.3 reassign by drag: `segment.reparent` gains placing the moved lines in the new region's order by page
   position, with an undo that restores the order entries (`restore_versions` does not); then the drag in Select.
3. The app halves listed as *Not built* in the spec: the validator on the export sheet; the Shape popover's
   Simplify slider with live preview; the two-second order overlay after a region merge; a bare K arming the Knife.
4. Stage 2.1 (lasso, ⇧-click removal, select all/same kind), 3.1 the Marker, 4.1 order by clicking.

Questions still open for the owner (do not guess): see the report's list.

---

## Report: what was done on 2026-11-13 (evening and night)

Twelve commits on `seg-editor`, `64428d59f..c55efd7bb`, pushed.

| Spec id | State now | What | Tests |
|---|---|---|---|
| `segment-editor.merge-lines` | OK | Join merges outlines, baselines and readings on every page (the Preview took the artifact combine on a page with a result; now Delete's door, #6419). Owner checked it in the app. | `test_segment_merge_lines.py`, `SegmentJoinTests` |
| `segment-editor.merge-regions` | PARTIAL | Merging regions moves their lines (and a line's words) to the kept one, placed by page position in every order; one undo. Not built: the order overlay. | `TestMergeRegions` |
| `segment-editor.regenerate-polygon-from-baseline` | PARTIAL | Edit › Segments ▸ Redraw Outline from Baseline and the context menu. No chord (⇧⌘R is Run Workflow on Selection's). Its Kraken call moved behind the seam (`kraken_runtime.polygonal_environment`): the previous session's direct import failed the seam test. | `test_regenerate_outline.py`, `RedrawOutlineTests` |
| `segment-editor.edge.self-intersecting` | PARTIAL | create/update store a self-crossing polygon as its outer boundary and answer `simplified`. | `test_segment_self_intersecting.py` |
| `segment-editor.edge.no-baseline` | OK | Redraw, the knife and Cut Words refuse and say so; Add Baseline (`segment.add_baseline`). | `test_segment_add_baseline.py` |
| `segment-editor.split-knife` | PARTIAL | `segment.split` with `cut_path` over many lines, one undo (`segment.unsplit_many`); Knife button and hold-K; the page says how many lines it left alone. Not built: a bare K arming it. | `test_segment_split_knife.py`, `KnifeStrokeTests` |
| `segment-editor.split-at-a-point` | OK | Split Line at Point (⇧⌘K), at the point last pressed. | `KnifeStrokeTests.splitAtAPoint` |
| `segment-editor.edge.knife-through-words` | PARTIAL | Words follow the part holding their centre; undo puts them back. Not built: splitting a crossed word. | `TestWords` |
| `segment-editor.edge.rtl-vertical` | PARTIAL | the knife follows the direction. | knife tests |
| `segment-editor.vertices` (Simplify) | PARTIAL | `segment.simplify` (pixels), Edit › Segments ▸ Simplify Outline at 2 px. No chord (⌥⌘S is Star's). | `test_segment_simplify.py`, `SegmentSimplifyTests` |
| `segment-editor.char-positions-kept` | PARTIAL | Kraken's per-character positions kept on the reading (read-given-lines path); Return cuts there (`cut: measured`). | `test_kraken_char_positions.py` |
| `segment-editor.cut-words-from-positions` | PARTIAL | `segment.cut_words`, after every Kraken read and on ⇧⌘W; ink-gap fallback; records source/confidence. | `test_segment_cut_words.py`, `CutWordsTests` |
| `segment-editor.cut-fallback-ink-gaps` | OK | | `TestFallback` |
| `segment-editor.validate-before-export` | PARTIAL | `GET /api/segments/document/{doc_id}/validate` (the spec said `/api/documents/{id}/segments/validate`; placed beside the other per-page segment reads). App half not built. | `test_segments_validate.py` |
| `segment-editor.export-carries-every-edit` | PARTIAL | The cut's source and confidence in PAGE `custom` and ALTO `WC`. | `test_cuts_in_page_and_alto.py` |

Runs on the final tree: build for testing succeeded (Dev Local, My Mac); the segment-editor Swift suites 30/30;
the engine suites above all pass; the 42 Kraken-read-path files 539 passed; the format and page-export suites
644 passed. `test_segments_matches_forwarding.py` passes again: it listed two routes missing on HEAD too
(on-rendition, reparent), now listed.

Known failures that are not ours (each also fails at the session's base `64428d59f`):
- `test_first_edit_conversion::TestUndoOfACombinePutsThePageBack::test_undo_then_redo_of_a_combine_round_trips_through_the_seam`.
- `test_imported_page_draws_its_boxes.py`: six fixture-drift tests. Regenerating the fixtures
  (`FICHERO_UPDATE_FIXTURES=1`) adds new fields (`counting_basis`, `read_by`) but reorders two readings, which
  breaks the Swift `ImportedPageDrawsItsBoxesTests.testChoosingTheFilesReadingOverACorrectionSendsReadingChooseAndUndoes`;
  so the old fixtures were kept. Needs someone who knows that ordering.
- Guards `check_docs_paths`, `check_spec_citations` (base 304 missing, now 301; allowed 269),
  `check_spec_no_duplicates` (image-enhancement.md).

Not seen by the owner in the app yet: everything except Join. Seen at engine level on a real Kraken page
(`/Volumes/Fichero Dev Disk/seg-worker-shots/`): merge, redraw, a knife over 22 lines, its undo.

Machine notes: the internal disk filled to 120 MB free mid-session (Xcode's logs and result bundles live on it);
the owner freed space. Late in the night the home folder started refusing reads and writes (EPERM), so
`~/seg-worker-report.md` could not be updated after the first part of the night; this file is the rest.

Questions for the owner:
1. Join's chord: the spec says ⌘J, the 2026-11-08 ruling and `MenuShortcutUniquenessTests` say ⌥⌘J (kept).
2. Redraw's ⌘⇧R is Run Workflow on Selection's; Simplify's ⌥⌘S is Star's. Which give way?
3. Lines measured on another image are refused by merge, redraw, knife and simplify, not carried. Right for now?
4. Story 2 draws the knife *between* two baselines of a fused line; the rule cuts only where a stroke crosses a
   baseline. Is a stroke along a gap meant to split a line with one baseline into two?
5. A split's (and a knife's) derived reading sits beside a person's original on the kept part, so neither counts
   there (existing behaviour). Should the derived one supersede?
6. Cut Words gives words a `reading_span` into the line's reading but no reading of their own. Should each word get
   one?
7. Words cut with ⇧⌘W: ⇧⌘W is Close in many Mac apps (the tests allow it). Keep?
