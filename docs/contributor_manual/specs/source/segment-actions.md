# Source Model — Segment actions: run a recipe step on the selected segments — Design Spec (#6069)

> Milestone: segment-editor
> Manual: the user manual's "Editing the lines" section (tracked by `segment-editor.md`) gains Run Step ▸ once built.
>
> Design-led (Testing Constitution). The owner owns this intent; tests enforce it; code makes them pass.
> **Status: DRAFT — written 2026-11-24 from the owner's scope comments on #6069 (promoted from later to now; the automatic re-run added in scope the same day).** Companion to `segment-editor.md` and `segment-editor-crud.md`, which it does not change.

## Intent

A person selects one or more regions, lines or words, in the segment editor, the Source pane, the Reader or the Segments list, and runs any recipe step that can run at that level on just the selection: Read, Re-read with another model, Translate, Find names, and the others the recipe has. The doors are the context menu (Run Step ▸ each step, with its model and Choose Model…), the menu bar, a key that runs the last step again, and an icon in the segment editor toolbar. Every door makes one call, `POST /api/recipes/project/start` with `steps` (the recipe's step ids) and `segments` (segment ids). The run is a recipe run in Activity, scoped to the selection. Each run writes a new pass and never overwrites the person's reading. After a segment is edited, the steps that read it re-run on it by themselves: local steps at once, paid cloud steps offered with their cost.

## Behaviors

- `segment-actions.run-step-on-selection` (#6069) [PARTIAL] — Start takes `segments` with `steps`: the recipe runs only those steps, only on those segments (the engine's `segments` selection, `workflows/selection.py`), and Activity shows the run as those steps on the pages the segments are on. *Built (engine):* `fichero-server/tests/unit/recipes/test_run_step_on_segments_6069.py` runs Read on two lines of an imported page through that exact call; the line beside them is not read; the page's text is untouched. *Not built:* the doors in the app (context menu, menu bar, key, toolbar icon), each step's model and Choose Model… in the menu, Activity naming how many segments a run covers.
- `segment-actions.step-that-cannot-run-says-why` (#6069) [PARTIAL] — a step that cannot run at the selection's level (a page-level step on a line) is refused in words before anything runs, never run on the whole page ("Find Names runs on pages, not on a line"). *Built (engine):* the same test file. *Not built:* the step shown disabled in the menu with that reason.
- `segment-actions.every-run-is-a-new-pass` (#6069) [PARTIAL] — a run on a selection writes a new reading on each segment (the working text is the person's choice); it never overwrites the reading that was there. *Built (engine):* the same test file reads the line again and finds both readings.
- `segment-actions.automatic-rerun-after-an-edit` (#6069) [MISSING] — after a segment's shape is changed, or it is split, joined or its type changed, the steps that read it re-run on it by themselves: local steps at once and quietly, shown in Activity; paid cloud steps are offered with their cost and never run unasked. A per-project recipe switch "Re-read edited segments" is on by default for local readers. Each re-run writes a new pass and never overwrites the person's reading.

## What the person sees

- **Where it opens:** select regions, lines or words in the segment editor, the Source pane, the Reader or the Segments list, then open the context menu: Run Step ▸ lists the recipe's steps, each with its model and Choose Model…. The same list is in the menu bar, a key runs the last step again, and a toolbar icon in the segment editor opens it.
- **Empty:** with nothing selected, Run Step is disabled and says "Select a region, line or word".
- **Loading:** a run shows in Activity as the step on the selection ("Read, 2 lines"); the selected rows show a busy mark until it ends.
- **Error:** a step that cannot run at the selection's level is disabled with the engine's words ("Find Names runs on pages, not on a line"); a refused or failed run shows its reason in Activity and leaves every reading as it was.
- **Acceptance:** with two lines selected, Run Step ▸ Read reads those two lines and no other, each gets a new reading beside the earlier one, and Activity shows the run.

## Build order

#### Step 1.1 — Run a step on the selected segments: the engine call (#6069)
- Behaviours: `segment-actions.run-step-on-selection`, `segment-actions.step-that-cannot-run-says-why`, `segment-actions.every-run-is-a-new-pass`
- Tests: fichero-server/tests/unit/recipes/test_run_step_on_segments_6069.py
- Size: M

#### Step 1.2 — The doors in the app (#6069)
- Behaviours: `segment-actions.run-step-on-selection`
- Tests: RunStepOnSegmentsTests (Swift, to write with the step)
- Depends on: 1.1
- Size: M

#### Step 1.3 — Re-read edited segments (#6069)
- Behaviours: `segment-actions.automatic-rerun-after-an-edit`
- Tests: test_reread_edited_segments_6069 (pytest, to write with the step)
- Depends on: 1.1
- Size: M

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | which steps are enabled for a level | `RunStepOnSegmentsTests` |
| Backend (pytest) | y | the Start call on segments | `fichero-server/tests/unit/recipes/test_run_step_on_segments_6069.py` |
| MCP | n | the generated tool takes the new field | `fichero-mcp/tests/test_mcp_generated.py` |
| CLI | n | generated from the route | `fichero-cli/tests/test_*.py` |

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual | y | the maintainer's own |
| Contributor | this spec | y | `docs/contributor_manual/specs/source/segment-actions.md` |
| Reference | endpoint reference | y | generated |
