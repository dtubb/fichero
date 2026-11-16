# Reading levels in the Inspector, the Reader and the recipe: the Fable look (2026-11-08, #6429)

Read from the code and the specs at origin/integration for the manager's hold ("Fable look first"); the step follows on the manager's word (segment-editor-crud, a Step 1.17, since the Inspector's sections are its Stage 1).

## 1. What exists

**Engine (all [OK], `source/readings-and-apparatus.md`):** five built-in levels in a fixed order, graphemic › as_written › expanded › regularised › modernised, plus `translation:<tag>` (`models/readings.py` `BUILTIN_READING_LEVELS`, aliases for old spellings, `canonical_reading_level`); every reading records its level (`source.reading.level-recorded`), its kind, who made it (`created_by`, `maker-set-by-engine`), what it read from (`read-from`) and its run; WHICH READING COUNTS is worked out per kind AND level (`counting_by_kind_and_level`, `source.reading.counts-per-level`: a person's expanded reading never replaces the line as written; a reading with no level competes at as_written, `BASE_READING_LEVEL`); a person records a choice (`POST /api/segments/{id}/readings/choice`, 403 for a model); a correction is a new reading (`representation.create`, stale check); the page's text is constructed from the counting readings of the working pass's lines (`source.model.page-text-is-constructed-from-the-segments`), today at as_written.

**Recipe (`source/models-chains-and-projects.md`):** "Into what" is a multi-select of levels (`source.recipe.into-what-is-a-multi-select`, `answers.normalise_levels`); the Normalise step runs once per level with the step's model and `start.LEVEL_PROMPTS`, each run writing readings at that level (`reading_level` in the run config), the runs named by the engine (`source.onboard.normalise-runs-named-by-the-engine`, `run_titles`).

**App:** the segment Inspector (`SegmentInspectorView.swift`) has a Text section that lists the segment's readings flat (`segmentService.readings(segmentId:)`) with Make This Count and Edit… (`InspectorReadingEditor`, #5201, the Reader's own `representation.create` and ⌘Z), and an Order section; the level is a field on each reading the row does not group by or name; the Reader and the Preview's inline text show the counting reading at as_written and have no level switch (`grep level Views/Reader` finds nothing); the recipe step row shows the step, its model and its settings, not what level it reads or writes; Compare compares READERS of one level (`CompareReadersView`), not levels.

## 2. What is missing (the owner's words, #6429)

A per-segment stack of levels (name, which step or model wrote it, which is shown, which is the working text the next step reads); a level switch in the Reader and the Preview; a compare of levels; the statement on a recipe step of which level it reads from and writes to.

## 3. The look

**Levels section in the segment Inspector** (and at the page level, as the Inspector's path already inspects a level: Page › block › line › word): one row per level in the fixed order, built from the readings the segment already has, grouped by `level`:
- the level's name (As written, Expanded, Regularised, Modernised, Graphemic, Translation (es→en)) and, in the row, the COUNTING reading's text at that level, in the segment's direction;
- under it in small words who made it: "by <model> in <run name>, <when>" or "by <person>, <when>" (`created_by`, the run, `read_from`); "corrected by <person>" when a person's reading counts;
- two badges: **Shown** on the level the window shows (the shared level state, below) and **Working text** on the level later steps read (as_written unless the recipe says otherwise, section 5);
- the verbs on a row: Show This Level, Make This Count (when the level has more than one reading, a disclosure lists the others, the existing choice), Edit… (the existing editor, at THIS level: the correction is a new reading at the row's level, the only change to the editor), Compare Levels…;
- a level the segment lacks is a quiet row "not made yet" with **Make <level>…**, which runs the existing Normalise step for that level on this page (or on these N lines) through the selection-scoped start of `ui/menus-and-commands.md` Step 1.1, priced first when the step's model is in the cloud; nothing is typed by hand unless the person chooses Type a Reading at that level (the existing Type a Reading…, with a level).
At the PAGE level the same rows count the page's segments per level ("Modernised: 112 of 118 lines") and Make <level>… runs on the page.

**One shared level state per window, `shownLevel`:** the Reader's text, the Preview's inline text and the Reader's Lines mode draw the counting reading at `shownLevel` for every segment, falling back to as_written where a segment lacks it (and saying so with a faint mark, not blank); the switch is one menu in the Reader bar (section 0 of the matrix brief: the Reader bar, Display menu) and under View › Reading Level ▸, one chord per level is NOT proposed (five chords is too many; ⌥⌘↑/↓ step through the levels, the uniqueness test deciding); the Inspector's Shown badge follows it. Default: as_written.

**Compare Levels:** the Compare component (`CompareViewModel`, Side by Side, Overlay, Wipe, Flip) with two LEVELS as its sides for the page or the selection, line by line, the differing words marked as it marks readers' disagreement; opened from the Inspector row's Compare Levels… and from Edit › Segments ▸ with a selection. No second implementation: the compare answer gains a `levels=a,b` way of choosing its sides where it chooses readers today (`GET /api/documents/{page_id}/compare-readers`), the one addition to the contract this look needs, named here for the manager (otherwise the sides can only be readers).

**The recipe step line, "reads <level>, writes <level>":** every step row in Set Up, Ready and Activity says what level it reads and what it writes, from the job table and the step's settings (`recipes/jobs.py` takes and gives; `reading_level` in the Normalise run config; readers write as_written; Names, Dates and Statements read the WORKING TEXT, as_written unless the recipe's "Into what" names another as the working level); the rule, stated once in `source/readings-and-apparatus.md`'s terms: a step reads the counting reading at the level its row names and writes at its own; the Inspector's Working text badge is that same level.

## 4. No new API, except the one named

The readings list, the choice, `representation.create` with a level, the Normalise step and its run titles, the selection-scoped start, the Compare component and the shared window state all exist. The one contract addition is the compare answer's `levels` sides; everything else is wording and layout. Tests: `tests/unit/api/test_reading_levels.py` (existing) extended for the compare sides and the editor's level; `InspectorLevelsTests.swift`, `ShownLevelTests.swift` (new, pure).

## 5. Answered by the owner (2026-11-08 13:10)

1. as_written is the DEFAULT working text, not always: the person compares levels and changes which level is the working text; the next step reads the working text. The levels are shown side by side: working text | normalised or modernised | translation.
2. Chords: yes, for the level actions, proposed and checked by the menus uniqueness rule.

The questions as asked:

1. Is as_written always the working text, or does "Into what" with a single level make that level the working text for Names and Dates? Recommended: as_written stays the working text unless the recipe says otherwise, and the step line shows it either way.
2. Chords: ⌥⌘↑/↓ to step through levels, or none (menu only)? Recommended: none at first; the menu and the Inspector badge suffice.
