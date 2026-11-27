# UI — The Recipes window — Design Spec (#6052, #4277)

> Milestone: recipes-window (proposed; the owner places it in `build-order.md`)
> Manual: TBD — a "Recipes" section: where recipes are kept, what a Recipe, a Step and a Tool are, how to reuse a
> step, how to use a recipe in another project, and that built-in recipes are copied before they are changed.
>
> Design-led (Testing Constitution). **Status: DRAFT 2026-11-27 — not approved; the owner approves.** Asked for by the
> owner on 2026-11-27 (paraphrased). No issue is filed yet — proposed: "Windows: Models & Cluster, Recipes, Training";
> until it is, each line cites the issue that owns its area today. The layout is the shared one
> (`windows-models-recipes-training.md`, which also holds the owner's open questions and the choice of the word Tool).
>
> **Owns / Does not own.** This spec OWNS the Recipes window: its sidebar, a recipe's detail, a step's detail, its
> Inspector, where recipes and steps are kept, and the main window losing its Workflows section. It does NOT own:
> designing a project's recipe in Set Up (`../source/recipe-designer.md`); a recipe run (`../source/recipes-run.md`);
> the canvas and its rules (`workflows.md`, `workflows.canvas.*`); a tool's fields (`workflow-node-config.md`,
> `nodeconfig.*`); runs as jobs (`activity-pane.md`); training a step (`training-window.md`).
> Tags: [OK] built · [PARTIAL] exists in part · [GAP] not built. Ids here are `recipes-window.*`.

## Intent

Today a person's workflows are a section of each project's sidebar, and a project's recipe is reached only through Set
Up. The Recipes window is one place for both: every recipe the person has, the steps recipes are made of, and the tools
inside a step. A **Recipe** has **Steps** in order; a **Step** runs one or more **Tools** wired together (today's
workflow); a **Tool** is one capability with its settings (today's node). Keeping recipes per person, not per project,
makes it easy to have many, to use one in another project, and to reuse a step in several recipes.

## The window

| Column | Shows |
|---|---|
| Sidebar | Search, then four sections: **This Project** (the front project's recipe, marked In Use, and any others it holds); **My Recipes** (the person's own, seen from every project); **Built-in** (shipped, locked); **Steps** (the step library, in the folders the workflow presets have today: Transcribe, Clean Up, Translate…). A row: name, number of steps or tools, and one state (In Use, Locked, Untested, Update Available). |
| Detail, a recipe | Its steps in run order, one row each: the step, its tools, its model and place, what it reads and writes. Add Step… (from the library), reorder, turn off, remove. A problem `check_recipe` finds is a sentence on its step. |
| Detail, a step | Its tools wired: the existing canvas editor. |
| Inspector | For a recipe: description, origin and version, the projects using it, its measures. For a step: model, place, reads and writes, the recipes using it, Train… For a tool: its settings (the node config's fields). A Runs tab lists Activity's rows for the selection. |
| Toolbar | New Recipe, Duplicate, Use in This Project, Run…, Share… |

## What the person sees

- **Where it opens.** Window › Recipes; Edit… on a recipe or step anywhere it has a menu; Set Up's "Open in the
  editor"; a run's row in Activity; Show in Recipes in the Training window. Each opens the window on that row.
- **Empty.** My Recipes, when empty, says "Duplicate a built-in recipe or make a new one" with both buttons. With no
  project open, This Project says to open one; the other sections still list.
- **Loading.** The sidebar draws from one read; a step's canvas appears when its definition has loaded, with the
  step's name and tool count shown before it.
- **Error.** A recipe that cannot be read is listed by its file name with the reason and Reveal in Finder; a step
  naming a tool this build lacks says which tool and still opens.
- **Acceptance.** In a project whose recipe has two steps (find lines, read): the window lists that recipe under This
  Project as In Use; choosing it shows the two steps in order; choosing Read shows its tools on the canvas and a tool's
  settings in the Inspector; Duplicate puts a copy under My Recipes; opening a second project lists that copy there
  too; the main window's sidebar has no Workflows section.

## Behaviours

Every test named is owed. Engine tests go in the engine's `tests/unit/recipes/`, Swift tests in the app's
`Tests/Unit/general/Views/RecipesWindow/`.

### A. Where recipes and steps are kept

- `recipes-window.library.one-read` — **[GAP]** (#6052, #4277; engine) one bounded, paged read returns the window's
  list: the front project's recipes, the person's recipes, the built-in recipes and the step library, each with its
  steps or tools counted, its state and where it is used. *Test (to write):* test_recipes_library, a project recipe a
  personal recipe and a built-in read back in their sections.
- `recipes-window.library.kept-per-person` — **[GAP]** (#4277; engine) a recipe or step the person makes is kept at the
  person's level and listed in every project (as `workflows.defaults.recipes-user-level-runs-library-pinned` asks for
  definitions); runs stay with the project they ran in. *Test (to write):* test_recipes_library, a recipe made in one
  project is listed in another.
- `recipes-window.library.project-keeps-a-copy` — **[GAP]** (#6052; engine) Use in This Project copies the recipe into
  the project with its origin and version; a newer version of the origin shows Update Available and is taken only when
  the person clicks Update; the project's past runs name the version they ran. *Test (to write):* test_recipes_library,
  an edited origin leaves the project copy unchanged until update.
- `recipes-window.step.reused-by-copy` — **[GAP]** (#6052; engine) adding a library step to a recipe copies it with its
  origin; the step says which recipes use it; a changed library step offers Update from Library on each copy and
  changes none by itself. *Test (to write):* test_recipes_library, a changed library step changes no recipe until
  update.

### B. The window

- `recipes-window.window.opens-on-the-row` — **[GAP]** (#6052, #4882; app) Window › Recipes opens one window in the
  shared layout (`windows.pattern.three-columns`); Edit… on a recipe or step, Set Up's "Open in the editor"
  (`designer.step.adjust-in-the-editor`), a run's row in Activity and Show in Recipes in Training each open it on that row. *Test (to
  write):* RecipesWindowTests, editOnAStepOpensTheWindowOnThatStep.
- `recipes-window.sidebar.four-sections-and-search` — **[GAP]** (#6052; app) the sidebar lists This Project, My Recipes,
  Built-in and Steps from the one read, each row with its name, count and state; the search field filters by recipe,
  step, tool, model or language. *Test (to write):* RecipesSidebarTests, theSidebarIsTheReadInFourSections.
- `recipes-window.recipe.steps-in-order` — **[GAP]** (#6052; app) a recipe's detail lists its steps in run order with
  each step's tools, model, place, reads and writes; Add Step…, reorder, turn off and remove write through the engine,
  and an order the recipe check refuses is shown as its sentence on the step, never saved silently. *Test (to write):*
  RecipeDetailTests, aRefusedOrderShowsTheChecksSentence.
- `recipes-window.step.detail-is-the-canvas` — **[GAP]** (#6052, #4882; app) a step's detail is the existing canvas
  editor showing its tools wired, with every `workflows.canvas.*` behaviour unchanged; a built-in step or recipe is
  read-only with Duplicate to Edit (`workflows.canvas.locked-preset-is-read-only`). *Test (to write):*
  RecipesWindowTests, aStepShowsTheCanvasAndABuiltInIsReadOnly.
- `recipes-window.inspector.follows-the-selection` — **[GAP]** (#6052, #4800; app) the Inspector shows a recipe's
  description, origin, version and the projects using it; a step's model, place, reads, writes and the recipes using
  it, with Train… opening the Training window on that step; a tool's settings as the same fields the node config shows
  (`nodeconfig.*`); and Runs, which are Activity's rows. *Test (to write):* RecipesInspectorTests,
  aToolShowsTheNodeConfigsFields.
- `recipes-window.recipe.use-run-share` — **[GAP]** (#6052, #6067, #4397; app) Use in This Project makes the recipe the
  project's (the Start plan shows it at once); Run… names the scope before anything runs
  (`workflows.defaults.declared-scope`) and the run is one Activity row; Share… and Import are the designer's
  (`designer.share.export-is-the-whole-plan`, `designer.share.import-checks-at-the-door`). *Test (to write):*
  RecipeDetailTests, runNamesItsScopeFirst.

### C. What leaves the main window

- `recipes-window.main-sidebar.has-no-workflows` — **[GAP]** (#4882, #6052; app) the main window's sidebar has no
  Workflows section and a workflow is no longer a thing its panes can select; recipes and steps are still run from a
  document's menu and from the bar, and Edit… there opens this window. *Test (to write):* MainSidebarHasNoWorkflowsTests,
  theSidebarSectionsOmitWorkflows.
- `recipes-window.words.recipe-step-tool` — **[GAP]** (#6052; app) every label in this window says Recipe, Step or
  Tool; "workflow" and "node" appear in no string the person reads here. *Test (to write):* RecipesWindowWordsTests,
  noLabelSaysWorkflowOrNode (a check over the window's string keys).

## What it replaces: the three existing specs, mapped

| Spec | Moves into the window | Stays where it is | Goes |
|---|---|---|---|
| `../source/recipe-designer.md` | Sharing: Share Recipe…, Use a Recipe…, the built-in recipes and recipe search list in the sidebar (`designer.share.*`); "Open in the editor" and "Adjust in the editor" open this window. | Set Up's whole journey: the material, the path, the stage pages, candidates and measures, Budget, Ready, Start. Set Up designs the project's recipe; "Start from a recipe" picks from this window's list. | Nothing. |
| `workflows.md` | The canvas editor (section A) as a step's detail; default, locked workflows and Duplicate to Edit (section E) as Built-in; folders of workflows (section F) as the Steps section's folders. | The bar that runs a chain over the selection (section D), in the main window; running, the run log and the trace (section C), which are Activity's and the Reader's. | The Workflows section of the main sidebar; a workflow as a selection in the main window's panes (`modes-to-panes.md`, the `.workflow(x)` row); `workflows.selection.library-row-opens-editor`, which becomes "Edit… opens the Recipes window". |
| `workflow-node-config.md` | All of it, unchanged: the node popover on the canvas, and the same fields as the Inspector's Tool tab. | The model chooser's one list, shared with Models & Cluster. | Nothing. |

## Build order

### Stage 1 — Engine: one library, kept per person

#### Step 1.1 — The library read and recipes kept per person (#TBD)
- Behaviours: `recipes-window.library.one-read`, `recipes-window.library.kept-per-person`
- Tests: test_recipes_library (to write)
- Size: M

#### Step 1.2 — A project keeps a copy; a step is reused by copy (#TBD)
- Behaviours: `recipes-window.library.project-keeps-a-copy`, `recipes-window.step.reused-by-copy`
- Tests: test_recipes_library (to write)
- Size: M

### Stage 2 — The window

#### Step 2.1 — The window, its sidebar and search (#TBD)
- Behaviours: `recipes-window.window.opens-on-the-row`, `recipes-window.sidebar.four-sections-and-search`
- Tests: RecipesWindowTests, RecipesSidebarTests (to write)
- Depends on: 1.1
- Size: M

#### Step 2.2 — A recipe's steps in order (#TBD)
- Behaviours: `recipes-window.recipe.steps-in-order`
- Tests: RecipeDetailTests (to write)
- Size: M

#### Step 2.3 — A step is the canvas; the Inspector follows (#TBD)
- Behaviours: `recipes-window.step.detail-is-the-canvas`, `recipes-window.inspector.follows-the-selection`
- Tests: RecipesWindowTests, RecipesInspectorTests (to write)
- Size: M

### Stage 3 — The main window lets go

#### Step 3.1 — Use, run and share from the window (#TBD)
- Behaviours: `recipes-window.recipe.use-run-share`
- Tests: RecipeDetailTests (to write)
- Depends on: 1.2, 2.2
- Size: S

#### Step 3.2 — No Workflows section in the main sidebar; the words (#TBD)
- Behaviours: `recipes-window.main-sidebar.has-no-workflows`, `recipes-window.words.recipe-step-tool`
- Tests: MainSidebarHasNoWorkflowsTests, RecipesWindowWordsTests (to write)
- Depends on: 2.3
- Size: M

## Accessibility identifiers

`recipes-window.sidebar.search` · `recipes-window.sidebar.row.<id>` · `recipes-window.recipe.step.<id>` ·
`recipes-window.step.canvas` · `recipes-window.inspector` · `recipes-window.toolbar.new` ·
`recipes-window.toolbar.duplicate` · `recipes-window.toolbar.use` · `recipes-window.toolbar.run` ·
`recipes-window.toolbar.share`.

## Open questions for the owner

Listed once, with recommendations, in `windows-models-recipes-training.md`: the word Tool (1), "workflow" off the
screen (2), sharing by copy (4, 5), Set Up's part (6), the bar (7), one window per app (10), the milestone (11).
