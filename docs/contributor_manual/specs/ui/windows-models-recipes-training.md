# UI — Three windows on one pattern: Models & Cluster, Recipes, Training — Design Spec (#6588, #6052, #5941)

> Milestone: recipes-window (proposed; the pattern's two steps are built with the first window that needs them)
> Manual: TBD — one paragraph in each window's own section saying the three windows share one layout.
>
> Design-led (Testing Constitution). **Status: DRAFT 2026-11-27 — not approved; the owner approves.** Asked for by the
> owner on 2026-11-27 (paraphrased). No issue is filed yet — proposed: "Windows: Models & Cluster, Recipes, Training";
> until it is, each line cites the issue that owns its area today.
>
> **Owns / Does not own.** This file OWNS the layout the three windows share (`windows.pattern.*`), the words Recipe,
> Step and Tool, and the questions below. Each window's own lines are in its own spec: Models & Cluster
> (`models-and-compute-window.md`, section A4 and Stage 6), Recipes (`recipes-window.md`), Training
> (`training-window.md`, section G and Stage 6). The house style they grow from is Activity's (`activity-pane.md`).
> Tags: [OK] built · [PARTIAL] exists in part · [GAP] not built.

## Questions only the owner can decide

Each has a recommended answer; the specs are written to the recommendation and change by one line each.

1. **What is the unit a Step runs called?** Recommended: **Tool**. A Recipe has Steps; a Step runs one or more Tools.
   The comparison is in "The words" below.
2. **Does "workflow" stay a word on screen?** Recommended: no. A workflow a person runs alone becomes a Recipe (often of
   one Step); a workflow's graph is a Step's wiring. The engine's package and route names stay as they are.
3. **"Stage" or "Step" in Training?** Recommended: Step on screen, everywhere outside Set Up. Set Up keeps Stage for a
   page that groups steps. The `training-window.*` ids keep their names.
4. **How does a project share a recipe?** Recommended: recipes and steps are kept per person, seen from every project;
   a project that uses one keeps its own copy with a note of where it came from, and takes a newer version only when
   the person clicks Update (the rule `source.recipe.update-is-clicked-not-applied` already gives a followed recipe).
5. **A Step reused in several recipes: one shared Step, or a copy in each?** Recommended: a copy in each, with Update
   from Library offered when the library's Step changed. A run stays reproducible; editing one recipe never changes
   another.
6. **Does Set Up stay the place a project's recipe is designed?** Recommended: yes. Set Up asks about the material and
   proposes the recipe; the Recipes window keeps, edits and shares recipes. Set Up's "Open in the editor" opens the
   window.
7. **Does the bar that runs a chain over the selection stay in the main window?** Recommended: yes; it lists recipes
   and steps and takes its name from the answer to question 2.
8. **What does Settings keep for AI?** Recommended: Allow cloud, the caps (permissions and limits), and one link,
   "Models & Cluster…". Keys, default models, downloads, the download location and clusters are in the window. (The
   spec lines of 2026-11-18 kept the defaults and the download location in Settings; this would supersede them.)
9. **Do the sidebar's search results replace the Models window's Found item?** Recommended: yes; results are listed in
   the sidebar under the search field, grouped by where they are, and Found goes.
10. **One window each, per app or per project?** Recommended: Models & Cluster and Recipes one per app (what they list
    is the person's, not a project's; a This Project section follows the front project); Training one per project.
11. **Order and milestone.** Recommended: Models & Cluster first (its lane is running), then Recipes as a new milestone
    `recipes-window` placed beside `workflows`, then Training after its engine stage. The line in `build-order.md` is the
    owner's to place.

## The words (question 1)

| Candidate | What it already means here | Verdict |
|---|---|---|
| **Tool** | One capability a workflow node runs: the engine's tool registry (`fichero-server/src/fichero_server/workflows/registry.py`), the `tool` id on every node, the canvas's palette of tools (`workflows.canvas.hidden-tools-in-palette`), and the tools the MCP server and chat offer. | **Recommended.** It is the word the code and the specs use for exactly this unit, so nothing is renamed and no word gets a second meaning. |
| Action | The audited action: every change to the library is one named action with an audit row and an undo (`fichero-server/src/fichero_server/actions`, `docs/contributor_manual/action-registry.md`); also what Shortcuts and App Intents call their units (`automation.md`). | No. A Step's unit would be a second, different "action" in the code, the specs and Shortcuts. |
| Workflow | A saved graph of tool nodes; what carries one recipe step out (`recipe-designer.md`, "The words"; `WORKFLOW_FOR_JOB` in `recipes/start.py`). | No. It is the wiring of a whole Step, not one unit of it. |
| Job | A step's kind in the job registry (`recipes/jobs.py`), and a row in Activity's one job model. | No. Taken twice. |
| Operation | A research operation (`research-operations.md`); a Prepare operation (`recipes/prepare_operations.py`). | No. Taken twice. |
| Node | The box on the canvas that holds a tool. | A drawing word; it stays in the canvas's code, not on screen. |

So, on screen: **Recipe** (the plan: ordered Steps) › **Step** (one job of the plan: Tools wired together, today's
workflow) › **Tool** (one capability with its settings, today's node). In code nothing is renamed: `recipes/`,
`workflows/` and `actions/` keep their names and meanings.

## The pattern (the layout all three share)

One `Window` scene and one pane kind per window, a `NavigationSplitView` in three columns:

| Column | Holds | Models & Cluster | Recipes | Training |
|---|---|---|---|---|
| Sidebar | a search field, then a sectioned list; a badge on rows needing the person | models, providers, this Mac, clusters, default models, downloads; search finds models here and online | this project's recipe, my recipes, built-in recipes, steps | recipes with their steps, steps that stand alone, trained models, runs |
| Detail | the selected row: a list's table, or one thing's page | a model's card, a provider's key and models, a cluster's state, the table of a group | a recipe's steps in order; a step's tools wired on the canvas | a step's ground truth, measure, teacher and students; a recipe's end score |
| Inspector | the selected thing inside the detail | a row's facts and run settings | a tool's settings; a step's model and place; runs | a candidate, an example or a run |

Search is always the sidebar's first control; the toolbar holds the window's few verbs; work that runs is a row in
Activity and never a second job list.

## What the person sees

- **Where it opens.** Each window opens from the Window menu and from the things that name it (a model's name in chat, a
  step's Train…, a recipe's Edit…), with that row selected in the sidebar.
- **Empty.** An empty sidebar section says what would fill it and offers the one verb that does; an empty search says
  what was searched and where.
- **Loading.** The sidebar draws from one read; the detail shows what it has and fills as answers arrive.
- **Error.** A row whose answer could not be read says so and keeps its last answer with its time.
- **Acceptance.** With the three windows open side by side, each has the search field at the top of its sidebar, a
  detail pane that follows the sidebar's selection, and an Inspector that follows the detail's selection.

## Behaviours

- `windows.pattern.three-columns` — **[GAP]** (#6588, #5941, #6052; app) Models & Cluster, Recipes and Training are each a
  `Window` scene with a pane kind, laid out as sidebar › detail › Inspector by one shared container view; the detail
  follows the sidebar's selection and the Inspector follows the detail's. *Test (to write):* WindowPatternTests,
  eachWindowIsTheSharedContainer (a source check: the three scenes construct the one container).
- `windows.pattern.search-leads-the-sidebar` — **[GAP]** (#6588, #5941, #6052; app) the sidebar's first control is a
  search field that filters the sidebar's own rows (every word needed, case and accents ignored) and says what it
  searched when nothing matches; a window whose search also goes online says so beside the field. *Test (to write):*
  WindowPatternTests, searchFiltersTheSidebarRows.
- `windows.pattern.opens-on-the-row` — **[GAP]** (#6588, #5941, #6052; app) a link to a thing one of the windows lists
  opens that window with the thing's row selected and shown, from any other window. *Test (to write):*
  WindowPatternTests, aLinkSelectsItsRow.
- `windows.pattern.work-is-activitys` — **[GAP]** (#6588, #5941, #6052; app) none of the three keeps a job list or job
  state: a download, a run and a training are Activity's rows, shown here by reading them. *Test (to write):*
  WindowPatternTests, noWindowOwnsAJobStore (a source check).

## What it replaces

Three layouts written one at a time: the Models window's source list and table (`models.window.is-activitys-shape`),
the Training window's split view (`training-window.window.opens-on-the-row`) and the workflow editor in the main
window's panes (`modes-to-panes.md`). The lines stay; the container they are drawn in becomes one.

## Build order

### Stage 1 — The shared container

#### Step 1.1 — One three-column container with a searching sidebar (#TBD)
- Behaviours: `windows.pattern.three-columns`, `windows.pattern.search-leads-the-sidebar`
- Tests: WindowPatternTests (to write)
- Size: S

#### Step 1.2 — Links open on the row; work stays Activity's (#TBD)
- Behaviours: `windows.pattern.opens-on-the-row`, `windows.pattern.work-is-activitys`
- Tests: WindowPatternTests (to write)
- Size: S

Then each window's own steps: `models-and-compute-window.md` Stage 6, `recipes-window.md` Stages 1 to 3,
`training-window.md` Stage 6.
