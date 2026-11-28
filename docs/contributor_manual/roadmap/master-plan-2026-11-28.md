# Fichero master review and roadmap — 2026-11-28

Read-only review of `origin/integration` at `176e8c0d40`, the builder's queue and journal, the briefs, the open issues
(2,235) and the owner's rulings to 2026-11-28. Nothing in the repo was changed and no issue was filed. Where a claim
was read from code but not run, it says "inferred". Dates are proposals; the lengths come from the measured pace in
section 9.

**The one-paragraph finding.** The app's core loop exists in the engine and is mostly reachable, but almost nothing a
person touches is finished: the spec lines for the areas the owner named are 60 to 95 per cent `[PARTIAL]` or `[GAP]`
(Activity 142 OK against 240 not; training window 1 against 32; Recipes window 0 against 13). Meanwhile the builder is
spread thin. Since 2026-11-25, of about 470 commits on integration, 128 are `docs(spec)`, about 130 are the harness
itself, and fewer than 60 change the app a person sees. In the last 14 days 188 issues closed and 513 were opened. The
fix is not more workers. It is one order, fewer lanes, a channel ladder that says what "finished" means, and a backlog
triage that stops the count growing.

---

## 1. The roadmap on one page

The ladder is the app's own channels (`harness/release-channels-and-feature-tiers.md`, #5299, answered 2026-10-04):
**Dev → Alpha → Beta → Release**. An area climbs a rung when it passes that rung's test:

| Rung | An area is here when | Who sees it |
|---|---|---|
| Dev | it exists; anything goes | the owner and developers |
| Alpha | every behaviour in its 1.0 scope is built and the owner has done its end-to-end test once | anyone who picks Alpha; badged "Alpha" |
| Beta | its spec lines in scope are `[OK]` with tests, no open P0/P1, its manual chapter is drafted, two weeks in Alpha without a data-loss bug | public beta testers; badged "Beta" |
| Release | two weeks in Beta with no new P1, its manual chapter and one video are published | everyone |

| Milestone | Dates (proposed) | Theme | Exit: "you can … end to end" | Climbs | Document and show |
|---|---|---|---|---|---|
| **Step 0** | Sat 28 – Mon 30 Nov | Stop, decide, cut | The owner has answered section 13; the builder runs 6 lanes on one phase; the backlog triage has started | nothing | nothing |
| **Phase 1 — Solid ground** → **Alpha 1** | 1 – 20 Dec (3 weeks) | Segments, runner, Activity; channels switched back on; triage finished | Open a folder of page photos, run Find Regions → Find Lines → Read on 200 pages, quit and relaunch mid-run and it resumes; watch Run → Step → File → Tool in Activity with no wrong spinner; fix lines in the segment editor and the edited lines re-read. Pick "Alpha" in Settings and get the Alpha build | Segment editor, runner, Activity: Dev → Alpha. Library, Reader, Import stay Release | Manual: "Your first project", "Correcting a page". Film: a 3-minute import-to-reading screen recording (private, for testers) |
| **Phase 2 — One vocabulary, one loop** → **Beta 1** (first public beta) | 21 Dec – 17 Jan (4 weeks, holiday slack) | Recipe › Step › Tool on every screen; Recipes window; Models & Cluster window finished; launch speed | Open the Recipes window, see this project's recipe as Steps, open a Step and see its Tool, change the Tool's model, run that one Step on a selection, see it in Activity under the same names. No screen says "workflow" or "chain" | Segment editor, runner, Activity: Alpha → Beta. Recipes window, Models & Cluster window: Dev → Alpha | Manual: "Recipes, steps and tools", "Activity". Article: "What Fichero is" for the site. Video: the core loop, public |
| **Phase 3 — Choose and compare** → **Beta 2** | 18 Jan – 14 Feb (4 weeks) | Set Up (the recipe designer), Compare on your pages, the model finder | On a new project, Set Up proposes a recipe with a reason for each model; "Compare on your pages" runs two readers on five of your pages and shows CER where you have corrected lines and says "agreement, not accuracy" where you have not; Use This changes the step; the finder lists only models this Mac can run, with a measured score or "unmeasured" | Set Up, Compare, Models & Cluster, Recipes window: Alpha → Beta. Training: Dev → Alpha | Manual: "Setting up a project", "Choosing a model". Video: Compare |
| **Phase 4 — Teach** → **Beta 3** (feature freeze) | 15 Feb – 14 Mar (4 weeks) | Training for the two steps that have trainers (Read a Line, Find Regions), measured; search and export made exact; the shell polished | Correct 100 lines, click Teach on Read, a Kraken reader trains on this Mac, comes back as a card with held-out CER beside the reader it replaces, Use This swaps it and Undo swaps it back; search finds what it says; an export re-imports unchanged | Training (reader, regions), Search, Export: → Beta. Set Up, Models, Recipes: Beta holds | Manual: "Teaching a reader", "Finding", "Exporting". Article: local models for archives. Video: Teach |
| **Phase 5 — A whole app** → **1.0 RC**, then **1.0** | 15 Mar – 11 Apr (4 weeks); 1.0 on or about 18 Apr | Release channel is a whole app (`channel.release-is-a-whole-app`); soak; zero open issues in 1.0 milestones; the manual and the site | On a clean Mac, download from the site on the Release channel, and do Phases 1 to 4's exits with nothing badged, nothing empty, no Dev surface visible | Everything in the 1.0 scope: Beta → Release | The Typst book 1.0, the MkDocs manual, the features-and-channels page, a launch article and a 5-minute film |
| **After 1.0** | from late April | Knowledge graph, people and concepts, the research window, sharing two Macs, iPhone and iPad, IIIF, clusters, App Store | each gets its own Beta | stay Dev/Alpha/Beta | as each graduates |

**What 1.0 is.** For a historian or archivist with an Apple-silicon Mac and a folder of page photographs or PDFs, mostly
handwritten. Five workflows polished end to end: (1) bring material in and organise it; (2) set up and run a recipe
that finds regions and lines and reads them, locally first, cloud only with permission and a cap; (3) correct the
reading on the page, by segment; (4) watch, stop and resume the work; (5) find text and export it in open formats.
One more ships in 1.0 **badged Beta** unless Phase 4 finishes early: (6) teach a reader from your corrections.

**Explicitly not in 1.0** (kept, hidden from Release, badged elsewhere): the knowledge graph and its paragraph, people
and lives, concepts and terms, reconstruct-the-record, the agentic research window, canvas organise, sharing between
two Macs, iPhone and iPad (TestFlight beta only), IIIF, cluster and Hugging Face training at scale, the App Store
build, word/character/stroke boxes beyond Find Words, audio and video tools, agents and automation, the Sequoia
floor (decided by the `platform-floor` spec), and the builder as a product.

**What is parked now to make the dates** is section 8.

---

## 2. Feature areas by channel, phase by phase

Today everything ships as one Dev build and `features.yaml` is stale: it has 56 features (7 release, 11 beta, 23 alpha,
15 dev), the 2026-10-04 ruling to move workflows, providers, activity and batches to Release was never applied
(`features.yaml`: Workflows, Activity, Providers are still `beta`), and the areas the owner cares about now have no row
at all: there is no entry for the segment editor, Recipes, the Models & Cluster window, Training, Set Up's Compare
(only `Wide Set Up`, `dev`), canvas organise or sharing.

Proposed tier of each area at the end of each phase (D Dev, A Alpha, B Beta, R Release; **bold** = climbs that phase):

| Area | Today (real) | Alpha 1 (20 Dec) | Beta 1 (17 Jan) | Beta 2 (14 Feb) | Beta 3 (14 Mar) | 1.0 (Apr) |
|---|---|---|---|---|---|---|
| Library, Reader, Import | R (listed) | R | R | R | R | R |
| Source pane and segment editor (regions, lines) | D | **A** | **B** | B | B | **R** |
| Recipe runner (run, stop, resume, one step on a selection) | D | **A** | **B** | B | B | **R** |
| Activity (pane, window, the run tree) | B (listed), D (real) | **A** | **B** | B | B | **R** |
| Image enhancement / prepare | D | D | **A** | **B** | B | **R** |
| Recipes window (Recipe › Step › Tool, the canvas) | not built | D | **A** | **B** | B | **R** |
| Models & Cluster window, the finder | D | D | **A** | **B** | B | **R** |
| Set Up (recipe designer), Compare on your pages | D (`wideSetUp`) | D | **A** | **B** | B | **R** |
| Cloud permission and caps | D | **A** | **B** | B | B | **R** |
| Training: Read a Line, Find Regions (this Mac) | D (no window) | D | D | **A** | **B** | B (badged) or R |
| Search (keyword, semantic) | R (listed) | R | R | R | **polish** | R |
| Export and round trip | D | D | D | **A** | **B** | **R** |
| Panes, sidebar, menus (the shell) | mixed | A | **B** | B | B | **R** |
| Find Words (word boxes) | not a step | D | **A** | A | **B** | B |
| Character boxes | action only | D | D | D | A | A |
| Stroke boxes | spec only | — | — | — | — | — |
| Knowledge graph, paragraph, tables | B (listed) | A | A | A | B | B |
| Sharing two Macs | D | D | D | A | A | B |
| iPhone / iPad | D (TestFlight) | D | D | A (TestFlight) | A | B (TestFlight) |
| Research window, canvas organise, people, concepts, IIIF | D | D | D | D | D | A |
| Training on a cluster or Hugging Face Jobs | D | D | D | D | A | A |
| MCP server, CLI | A | A | A | A | B | B |

### 2.1 What turning channels back on needs (checked against the code)

| Piece | Built? | Evidence | Needs |
|---|---|---|---|
| Tier per feature, generated to Swift, Python and a docs page | **Built** | `features.yaml`; `scripts/gen_feature_tiers.py`; `scripts/check_features_freshness.py`; `docs/reference_manual/features.md`; `fichero-server/src/fichero_server/api/feature_tiers_generated.py` | new rows for the missing areas; the 2026-10-04 moves applied |
| App hides a feature below the build's tier | **Built** | `FeatureManager+Accessors.swift:96` (rule), `:38-87` (tier from `Info.plist`, fail closed to release) | read the chosen channel, not only the baked tier |
| Engine hides routes below the tier (404 `feature_tier_gated`) | **Built** | `api/main.py:3079-3142` | nothing for routes; **steps and tools have no tier** (2.2) |
| A channel choice in Settings | **Not built** | `channel.the-choice-is-in-settings` [MISSING]; no "channel" in `GeneralSettingsView.swift` | the popup, persistence, Relaunch Now; the General tab moved to Release (it is `beta`) |
| One binary, tier chosen at run time | **Not built** | `channel.one-shipping-binary`, `.features-follow-the-channel` [MISSING]; five build configurations still bake the tier (`scripts/tier_build_map.sh`) | resolve tier = stored channel, default from `Info.plist` |
| Sparkle: four channels on one feed | **Half** | `SparkleUpdater.swift:33`: only `dev` or nothing; `scripts/appcast_upsert.py` writes public and dev items | `allowedChannels` = the chosen channel and every more stable one; appcast items tagged alpha/beta/dev |
| The lane publishes to a channel; promote without rebuilding | **Not built** | `channel.the-lane-publishes-to-a-channel`, `.promotion-is-one-command` [MISSING]; `release-all.sh:203-208` has `--public`, `--tier` | `--channel <c>` and `promote <build> <channel>` |
| TestFlight groups per channel | **Not built** | TestFlight archives the dev tier only (`release-all.sh:19`); `tier_build_map.sh` names an `App Store` scheme the spec says points at a missing target | two groups (internal = Dev, external = Beta); iOS tier baked at archive (ruled) |
| A Release build that is a whole app | **Not built** | `channel.release-is-a-whole-app` [MISSING]; the spec records that a Release build cannot transcribe a page | the tier moves above, then a UI test that runs the core loop at `release` |

This is about 28 `[MISSING]` lines; at 3 to 5 lines a step it is 7 to 9 landings, two lanes for one week, in Phase 1.

### 2.2 Tiers for recipe steps and tools (not built; proposed)

Today neither registry carries a tier. `recipes/jobs.py:32-49` (`Job`) has `since` and `needs_a_model` and nothing
about readiness; `workflows/types.py:696` (`ToolDef`) has `category`; tools are gated only in groups by
`features.yaml` rows such as "Workflow tools audio", read in Swift (`FeatureManager+Accessors.swift:156-170`), so the
engine and the MCP list every tool whatever the channel.

Proposed, one rule in one place:
- `Job` gains `tier` (required at registration, refused when missing, exactly as `needs_a_model` is at
  `jobs.py:66-71`); `ToolDef` gains `tier`. Both are filled from `features.yaml` (new `steps:` and `tools:` sections)
  so the site and the manual list them from the same file.
- `all_jobs()` and the tool registry's reads take the running tier and leave out what is below it. That one filter
  covers Set Up, the Recipes window, the run sheets, the Run Step menus and the MCP's tool list.
- On Alpha and Dev a hidden-elsewhere step or tool is shown with its badge.
- `check_recipe` (`recipes/recipe.py:109`) never deletes or rewrites. For a step whose job is below the channel it
  adds one sentence, in the style it already uses for an unknown job (`jobs.py:207`): "step 4 (Find Words) is an
  Alpha step; this copy is on Beta. Choose Alpha in Settings › General, or remove the step." Start skips that step
  with the reason on its row (the existing "has no model" skip), and `unmet_inputs` then names any later step that
  needed its output. Results a hidden step already made stay visible.
- A **model** is graded too, by measurement rather than tier: "measured on your pages", "measured by its maker",
  "unmeasured". Release proposes only the first two as a default.

First tiers: `find-regions`, `find-lines`, `read-a-line`, `read-a-page`, `correct`, `put-in-order`, `leave-out`,
`prepare-the-image`, `export` Beta-bound; Find Words Alpha; `find-signs`, `identify-signs`, `trace-a-drawing`,
`transcribe-speech`, `find-a-tables-cells`, `refine-shapes`, character and stroke cuts Dev.

### 2.3 The channel UX in the app

In the spec: the popup in Settings › General › Software Update with one line saying what the channel is; the choice
kept per user; applies at next launch with Relaunch Now; the pane visible on every channel; an empty surface names
the channel; a client hides what its host does not serve; per-feature switches stay internal.

Missing from the spec (add to it; small):
1. **About** shows the channel and build beside the version ("2026.12.20 (812) — Beta"), and links to the popup.
2. **Badges.** A feature below Release, shown because the person chose a wider channel, carries a small "Alpha" or
   "Beta" capsule: on its window title, its sidebar section, its Settings tab, its menu item, and on a step or tool
   row in a recipe. One shared view, one accessibility id.
3. **What you get.** Under the popup, "What's in this channel…" opens the generated list (2.4) filtered to the
   chosen channel, so a person sees what switching will add before they switch.
4. **Opting in.** First choice of Alpha or Dev shows one alert: what may break, that a library is never opened by
   an older build, and that moving back waits for the stabler channel to catch up (`channel.no-downgrade`, [OK]).
5. **The owner's and developers' view.** A Debug menu item "Feature Tiers…" (Dev channel only): the full table, the
   tier, the internal switch, the engine's answer for the route, and a per-launch override for testing "as Release".
6. **A hidden feature reached by a link** (a saved pane, a recipe step, an MCP call) says which channel has it, never
   a blank pane or a raw 404.

### 2.4 The same list on the site and in the manual

One source already exists: `features.yaml` → `gen_feature_tiers.py` → Swift map, Python map and
`docs/reference_manual/features.md` (in the MkDocs nav as "Feature Matrix"). Extend it rather than add a second file:
- Add public fields to each row: `public_name`, `summary` (one sentence a researcher reads), `manual` (the chapter),
  `since`, and `steps:` / `tools:` rows (2.2). Internal fields (flags, route prefixes, notes) stay out of public
  output.
- The generator also writes `features.public.json`: each feature with its status in each channel ("in Release",
  "in Beta", "in Alpha", "in development"). The site's page (tubb.ca/apps/fichero, an Eleventy build deployed with
  the Netlify CLI) reads that file; the MkDocs manual includes the same table; the Tinderbox master gets it as one
  generated note, and each chapter head carries its feature's badge.
- The roadmap's public view is `roadmap.yaml` (section 10) reduced to: phase name, theme, what graduates, and a
  quarter, not a day. No lane names, issue counts, costs or machine names.
- A guard (`check_docs_publication` already exists) refuses archive names, box ids, places and personal paths in any
  generated public file (owner ruling 2026-11-13). One deleted experiment's docstring named private research
  material; none of it is in these outputs.

---

## 3. The vocabulary

### 3.1 What the code has today

| Thing in the code | Where | What it is |
|---|---|---|
| Recipe | `recipes/recipe.py`, `recipe.yaml` (`steps`, `overrides`) | the plan for a project |
| Job | `recipes/jobs.py:32` (`Job`: `takes`, `gives`, `layer`, `compare`, `needs_a_model`) | the **kind** of step: what is asked, what goes in and comes out, how two runs of it are compared. "A job is not a tool" (`jobs.py:12`) |
| Step | a recipe's `steps[]` entry naming a job, with model, place, prompt | one job in one recipe |
| Stage, Card | `recipes/stages.py:40`, `runner.py:317` | Set Up's page that groups steps; the runner's unit. The engine uses "step" for three different things (a stage's job ids, a step run, a tree row) |
| Workflow | `workflows/`, 60 shipped presets; `WORKFLOW_FOR_JOB` (`recipes/start.py:27-43`) | a saved graph of tool nodes. Each job maps to **one** workflow, with alternates chosen by the model: `read-a-line` → `transcribe_kraken`, or `read_lines_kraken_vision` when the pick is a vision model (`start.py:58`), or Apple Vision lines (`start.py:60`) |
| Node | `NodeDef` (`workflows/types.py`), the canvas in `fichero/fichero/Views/Workflow/Canvas/` | one box on the canvas holding a tool and its settings |
| Tool | `workflows/registry.py` (`_TOOLS`, `_TOOL_DEFS`, about 135 defs, 114 files in `workflows/tools/`) | one capability with ports, a config schema and whether it uses a model |
| Sub-workflow | `workflows/subworkflow.py` | a workflow used as one node of another, with a typed contract |
| Chain | `Views/Workflow/Library/WorkflowChainListView.swift`, `ChainEditorView.swift`, `/api/chains`, the workflow bar's `stagedWorkflowChain` | several workflows run in order over a selection: a recipe by another name |
| Action | `fichero_server/actions`, `docs/contributor_manual/action-registry.md` | the audited, undoable change. Taken |
| Candidate, pick | `source/recipe-designer.md` "The words" | a model and the place it runs that a step could use; the one it does |

### 3.2 The question the owner asked

The draft spec (`ui/windows-models-recipes-training.md`, "The words") and the 2026-11-28 ruling say: Recipe › Step ›
Tool, "a Step runs one or more Tools wired together; that wiring is today's workflow; a Tool is today's node". That
leaves the owner's example without a word. "Read the lines" is the step. Kraken can do it. A graph of a Fable model
and a Google model can do it. Under the draft, the first is one tool and the second is "the step's wiring", so the
two things a person chooses between, compares and trains against each other have different names, and the wiring
has none.

### 3.3 Recommended: a Tool can be made of Tools

- **Recipe** — the plan: Steps in order.
- **Step** — what is asked for, in the researcher's words: "Read the lines". It says what it takes and gives, and
  how its result is measured. A Step **uses one Tool**.
- **Tool** — what does it. A Tool is either
  - a **basic tool**: one capability with its settings (the Kraken line reader, the YOLO region finder, one model
    call with a prompt), or
  - a **compound tool**: tools wired together and saved under one name, with the same inputs and outputs as a
    basic tool (Kraken finds the lines, a vision model reads each, a second model checks it).
  The canvas is where a compound tool is built. The boxes on it are tools. "Node" stays a word in the canvas's code.
- **Model** — the weights a tool runs, and the **place** it runs. A tool that needs a model has a model slot.

So the answer to "is a tool a node or a whole graph?" is: both, because a graph of tools is a tool. That is how every
comparable system that has the problem solves it (3.5), it is already in the engine (`subworkflow.py`), and it makes
the three things the owner wants fall out without another word:
- **Choosing.** A Step's candidates are Tools. "Kraken", "YOLO" and "Fable then Google" are three tools for one step.
- **Comparing.** Compare on your pages compares tools on a step, by that step's measure.
- **Training.** See 3.6.

"Workflow" leaves the screen: a workflow a step uses is a compound tool; a workflow a person runs by itself is a
Recipe of one Step. "Chain" leaves the screen: a chain is a Recipe (an unsaved one in the bar is "Run steps…").
"Action" keeps its one meaning. Nothing in the code is renamed; `recipes/`, `workflows/`, `actions/` keep their names.

### 3.4 Alternatives

- **B. The draft as written** (Step = the wiring of Tools; Tool = node). Fewest changes to the draft specs. Cost:
  no name for the thing compared and trained; "a step's wiring" has to be said every time; a step and its wiring
  become one thing, so two ways of doing one step look like two steps.
- **C. Four levels: Recipe › Step › Method › Tool** (Method = the wiring; Tool = node). Clear and not recursive.
  Cost: a fourth word on every screen, and the owner already uses "method" for what a whole recipe is ("each recipe
  is its own method", 2026-10-03).

### 3.5 What others call these levels

| System | The plan | A unit of it | A unit made of units | The thing that runs | Notes |
|---|---|---|---|---|---|
| ComfyUI | workflow | node | group node / subgraph | model (checkpoint, LoRA) loaded by a node | a subgraph is used as a node |
| Node-RED | flow | node | subflow | — | a subflow appears in the palette as a node |
| n8n | workflow | node | sub-workflow (Execute Workflow node) | credential / model on the node | |
| Apple Shortcuts | shortcut | action | "Run Shortcut" action | app intent | "action" is Apple's word for the unit; it is why Fichero should not reuse it |
| Airflow | DAG | task (an instance of an operator) | TaskGroup / sub-DAG | operator | operator : task = Fichero's job : step |
| Nextflow | workflow | process | subworkflow | container / tool in the process | pipeline › subworkflow › process (module) |
| Transkribus | (none; a job per action) | job | — | model (layout, text recognition, "Super models") | the person picks a model per task; trains models; measures CER |
| eScriptorium | (none; per-document tasks) | task (segment, transcribe, align, train) | — | model (segmentation, recognition) | |
| Kraken | a chained command line (`binarize segment ocr`) | subcommand | — | model (`.mlmodel`) | |
| **Fichero (recommended)** | **Recipe** | **Step** | **compound Tool** | **Tool**, running a **Model** at a **place** | |

The archive tools (Transkribus, eScriptorium, Kraken) have no word above "task" and none for a composite; their unit
of choice and training is the model. The automation tools all let a group of units be used as one unit. Fichero needs
both, which is why the recommended model has Step (the task), Tool (the unit, which may be a group) and Model.

### 3.6 Where a trained model plugs in

Three statements, each true in the code today:
1. **The measure belongs to the Step.** Each job declares how two runs of it are compared (`jobs.py:37`, the `compare`
   field: CER/WER for readings, precision and recall for shapes and lists) and the engine scores against held-out
   corrected pages (`training/evaluation.py`, `workflows/transcription_accuracy.py:327`).
2. **The weights belong to a Model, and a Model sits in a basic Tool's slot.** A trained reader lands as a model card
   in the project (`training/landing.py`, `project_models.py`), never the default until chosen.
3. **A Step picks its Tool and Model**, per project or per folder: `recipe.overrides[]` =
   `{step, scope, folder_id, model, card, runs_on, cer, policy, because, …}` (`recipes/bakeoff.py`, `use_this`).

So: **fine-tuning** changes the model in a basic tool. **Distilling** takes the step's current tool as the teacher,
whatever it is made of, and produces a basic tool with a new local model as the student; the gate
(`training/gate.py`: better, too close, worse, not measured, against a noise band) is run at the step. A compound
tool is therefore trainable as a whole, by replacing it. Its inner tools are trainable only where the inner tool does
a registered job (a "read a line" tool inside a compound tool is still measured as read-a-line). The per-step registry
that already exists, `DISTIL` in `jobs.py:163`, is the right home; it has a student for only two steps.

### 3.7 The segment levels, and what makes each

The detailed inventory is the `spec-seg-metadata` lane's job. This is only the placement.

| Level | Step that makes it | Tool today | Stored | Trained model fits | Tier at 1.0 |
|---|---|---|---|---|---|
| Region | Find Regions (`find-regions`) | Kraken blla regions (default) or YOLO DocLayNet (`recipes/regions.py`, `llm/yolo_runtime.py`); a vision-model and Apple Vision path in `tools/detect_regions.py` | yes | **built**: YOLO trained on this Mac from drawn regions (`training/yolo_local.py`, mAP50) | Release |
| Line | Find Lines (`find-lines` → `detect_regions_kraken`) | Kraken blla (baseline and polygon); Apple Vision line boxes for print | yes | **not built**: no line-finder trainer (`DISTIL["find-lines"]`) | Release (untrained) |
| Word | **none today**; Find Words is #7111 part 14 | the action `segment.cut_words` (`api/routes/document/segments.py:4676`): the reader's CTC positions, else ink gaps | yes (`kind="word"`, `cut_source`) | rides on the line reader: a better reader gives better cuts; no trainer of its own | Beta |
| Character | none | the action `segment.cut_characters` (`segments.py:4932`) from Kraken `char_positions` (`kraken_runtime.py:120`); [PARTIAL] | yes | rides on the line reader | Alpha |
| Stroke | none | nothing; the Pencil trace is spec only (`source/segment-editor.md:263-265`) | no | none | not in 1.0 |

Attributes: region type (the finder's label, or the person; stored as `kind_raw`); region name (#6512, not stored,
inferred); language and script (Find the Script → `classify_script`, or the person); direction (Kraken or the person);
orientation (#7108, not built); hand (no column found, unverified); reading order (Put in Order, or the person;
managing orders is #7109); confidence (the reader or the cut).

Order: regions and lines are Phase 1. Find Words becomes a real step (a job with a tier) in Phase 2, after the
vocabulary, so it is born as a Step with a Tool. Characters stay an action until after 1.0. Strokes need a spec first.

### 3.8 Owner decisions in this section

The names (3.3 against B or C); whether "compound tool" is said on screen or only "Tool" with "made of 3 tools"; what
the bar's unsaved chain is called; whether a Step may hold more than one Tool in parallel (recommended: no; that is a
compound tool). They are questions 1 to 3 in section 13.

---

## 4. What is really working and what is broken

Tags are counted at `origin/integration`. "Built" means reachable in the app, not "the engine has a route".

### 4.1 Recipe designer (Set Up) — built in the engine, hidden in the app

Spec `source/recipe-designer.md`: 17 OK, 31 PARTIAL, 31 GAP, 2 BROKEN.
- **Built:** the engine side (`recipes/how.py`, `defaults.py`, `step_choices.py`, `where_it_runs.py`, `start.py`;
  routes `/api/recipes/questions`, `/defaults`, `/project/start`, `/project/steps/use-candidate`).
- **Built but hidden:** the How step, the pager, the condition tick boxes and the reasons for defaults are all behind
  `wideSetUp`, tier `dev` (`features.yaml` "Wide Set Up": "off in release until ratified"). The spec's own lines say
  "built behind `wideSetUp`, not yet seen in a build" (lines 217, 296, 313, 353, 367, 373). Those lines are tagged
  [OK] for the engine while the person sees the old Set Up.
- **Built but broken:** `defaults.py` is "not yet applied by `assemble.py`" (lines 240, 477, 514, 518), so the table
  of defaults is shown as text and does not choose the models. Hugging Face Jobs has two ids: `hf-jobs`
  (`where_it_runs.py:13`) and `huggingface-jobs` (`start.py:868`), #6816 [BROKEN]. `use-candidate` leaves the old
  model's name on the step, #6815 [BROKEN]. #6167, #6168: Leave Out, Statements and Entities cannot choose a model.
- **Never built:** `designer.how.model-kind-decides-the-compare` (the engine never reads `answers.how.model_kind`),
  `designer.defaults.says-why-on-the-stage-pages`, the budget lines.

### 4.2 A/B: "Compare on your pages" — three things share the name; the one the owner wants shows agreement, not accuracy

- **The bake-off** (`recipes/bakeoff.py:387`; `BakeoffSection.swift`): real CER and WER against a person's corrected
  lines (`training/evaluation.py:482-492`). It refuses below 100 corrected lines on 2 pages (`bakeoff.py:52`, `:398`),
  so on a new project the block is hidden (`BakeoffStore.isShown`). It never downloads: a local candidate not on
  this Mac is "not scored" (`bakeoff.py:96-118`), and with none scoreable it refuses (`:404`).
- **The stage Compare** (`recipes/samples.py:315`; `CompareReadersView`, `StageCompareWindow`): runs up to 3
  candidates on a copy of the pages. Its number is `None` unless lines on those pages were corrected
  (`samples.py:743`); otherwise it shows "agreement" between the candidates (`:675`), which is not accuracy, yet
  `designer.measure.on-your-pages-first` is tagged [OK] (line 778). With one model pre-ticked it compares nothing
  (#6408). The chooser vanishes when the finder list is empty or errors. A cloud candidate raises a 402 unless the
  cost is accepted. A local candidate only queues its download and waits silently (#5806, #5687). And the whole view
  is behind `wideSetUp`. #5727 ("the A/B in Set Up does not work") is open.
- **Two unrelated compares** that also say "Compare models": the prompt fan-out (`workflows/model_comparison.py`,
  `Views/Chat/ModelComparison/`, the workflow bar's Compare) and the diff of two workflow runs
  (`workflows/run_comparison.py`). Neither measures against ground truth.
- **Never built:** the compare row's sentence (`designer.compare.row-sentence` [MISSING]), "says its page count",
  whole-page measure, seconds and memory, cloud models in the bake-off (#5718), every kind of reader (#5533).

### 4.3 Model finder (Models & Cluster window) — works for one case, guesses for the rest

Specs: `ui/models-and-compute-window.md` 5 OK, 31 PARTIAL, 20 GAP, 2 BROKEN; `ai/where-models-run.md` 5, 22, 21, 2.
Why it is inaccurate (`recipes/discovery.py`, `api/routes/system/recipes.py:1692`):
1. The window asks one question only: the first open project, the reading step, the first material
   (`ModelsPaneView.swift:~162`, `ModelFinderStore.readingJob`). With no project open it says "Open a project".
2. Recall rests on Hub tags and repository names: `pipeline_tag` plus `filter=[mlx, <language tag>]` plus keyword
   searches (`search_hugging_face`, `discovery.py:1409`). An exact-tag AND misses a model tagged `lat` instead of
   `la`, or untagged. `reads_text()` (`:1169`) decides "is a reader" from tags and the name.
3. Ranking is language overlap, then a count of keyword hits capped at 6, then downloads (`rank`, `:~1560`). No
   measured score. Only the top 5 cards are read for a stated CER and a licence; the rest say "unmeasured".
4. It lists what Fichero cannot run (Kraken models on the Hub by another route, TrOCR, GGUF, PyLaia) as "cannot run
   yet".
5. Fit is computed for MLX models only (`llm/local_inference.py:193`); others get none; the Fit column is [GAP].
6. Online search needs egress allowed and a project; otherwise it answers from a cache that refreshes daily.
7. The search box matches names only (`ModelCandidateRules.swift:68`).
8. Hugging Face is searched only for steps in `STEP_SEARCHES`; other steps never go online.
- **Never built:** one search over local models, providers and the Hub (line 315); search by step, script, language
  or period; "Use for…"; the Settings panes were moved in whole (`AISettingsView(placement: .window)`,
  `ModelsPaneView.swift:141`), not redesigned as the 2026-11-24 ruling asked.

### 4.4 Recipe runner — the strongest area; reliability is half-tested

Specs: `source/recipes-run.md` 56 OK, 27 PARTIAL, 9 GAP; `compute/runner-reliability.md` 16 OK, 37 PARTIAL, 12 GAP.
- **Built:** a run of a recipe's steps over documents or a folder (`recipes/runner.py:131`), redo of chosen steps,
  one step on selected segments (`RunStepOnSegmentsMenu`, #6069), an edited line re-read by its local model
  (`recipes/reread.py`), adoption of a run paused at quit (`runner.py:511`).
- **Built but weak:** resume across a relaunch (#6584, #6595 open: twinned paused jobs); Pause and Stop on recipe
  runs (#5933); `runner.results.no-silent-loss` and `counted-done-only-with-a-result` [PARTIAL]; the failure alert
  `run.fail.*` mostly [GAP] (#6354); the 100-page finish and flat-memory lines [GAP] (#6212).
- **Never built:** a page-level scope (only documents, folders, segments); a Run sheet with a choice of input reading
  (#7112); the owner's 5,000-pages-overnight test as a standing check.

### 4.5 Activity — a wide pane over a tree it does not show

Spec `ui/activity-pane.md` (571 KB): 142 OK, 206 PARTIAL, 34 GAP.
- **Built:** the pane and window with Runs, Files, Recipes, Cost, Where, Archived; the engine's job tree of a run,
  its steps and their pages, with state, times, cost, model, counts (`workflows/activity.py:708-760`).
- **#7118, never built:** the pane discloses run → files only; steps are a trail cell (the spec's decision 2, not yet
  re-tagged). The engine has no tool-call level: "the rows under its steps are lane work, not pages, and a page read
  without the lane has no row at all" (`activity.py:1209-1211`). So Run → Step → File → Tool needs an engine change
  first, then the outline.
- **#7119, built but wrong:** the spinners do not come from the job tree. Four sources feed one spinner
  (`SidebarRowLabelCore.swift:106-145`): `childrenLoading`, `workflowRunning`, `documentProcessing`,
  `containerProgress`. A folder rolls up direct children only (`SidebarItemRow.swift:219-244`). A recipe run appears
  never to set a page to processing (inferred), which is why some rows spin and others do not. After an engine
  restart the app's status is not re-derived (inferred; #4384, #4346 open). The fix is one source: the engine's tree.

### 4.6 Recipes window — never built

`ui/recipes-window.md`: 0 OK, 13 GAP, a draft of 2026-11-27 with no issue. No `Window` scene; no engine read of a
recipe library, no per-person recipes, no copy-with-origin. The canvas it would hold exists in the main window
(`Views/Workflow/`), with "Workflow" and "Chain" on its labels.

### 4.7 Training — trainers exist; no window, no loop, two steps of twenty

Specs: `compute/distillation.md` 4 OK / 49 not; `jobs-and-fine-tuning.md` 24 / 74; `correct-measure-distil.md` 5 / 25;
`training-and-evaluation.md` 13 / 55; `ui/training-window.md` 1 / 32.
- **Built:** a Kraken reader trained on this Mac (`training/local.py`, CPU) or on Hugging Face Jobs
  (`hf_kraken_train.py`); YOLO regions on this Mac (`yolo_local.py`); a vision-model LoRA on Hugging Face Jobs,
  converted to MLX on landing (`hf_vision_lora_train.py`, `mlx_landing.py`; the spec says never trained on real
  pages); held-out CER under four policies stored on the card; the gate; Use This.
- **Never built:** a Training window (no such view; only Set Up's offers); the loop that chains teacher → lines →
  train → measure → gate → adopt (#6052); trainers for Find Lines, names (#5536), review, statements; cluster
  training (`train_offers.py` says "no training path"); undo of a switch
  (`training-window.switch.never-silent-always-undoable` [GAP]); model versions.
- **Unmeasured steps:** every step except Read a Line, Read a Page and Find Regions has no error metric in code
  (extraction precision and recall are #5545, spec only).

### 4.8 Segment editor — the tools work; the owner's list has not landed

Specs: `source/segment-editor.md` 15 OK, 66 PARTIAL, 35 GAP; `ui/segment-editor.md` 30, 42, 15;
`segment-editor-crud.md` 0, 30, 76.
- **Built:** draw rectangle and polygon with a kind, Knife, Lasso, Reshape, Join, Convert Kind, split and merge, cut
  words and characters, each undoable; the Inspector form.
- **Built but broken:** #7034 drawing a new region; #7115 boxes appear only when the whole run ends; #7080; #6734
  Brush records nothing; #7111 parts 6, 7, 13 (drag reorder, selection lost on resize, dead reorder buttons).
- **Never built:** all of #7111 (`git log --grep 7111` is empty; the batch is with the worker now); orientation
  (#7108); the Orders sheet (#7109); a line's other readings in the editor; duplicate, copy, paste; expand one axis
  (#6735); Find Words as a step; strokes.

### 4.9 Built but broken, against never built

| | Built but broken or hidden | Never built |
|---|---|---|
| Designer | hidden behind `wideSetUp`; defaults not applied; two place ids | reasons on stage pages; model kind decides the compare |
| Compare | shows agreement as if accuracy; one-model compare; silent waits | the row sentence; cloud in the bake-off; time and memory |
| Finder | one pinned query; tag guessing; lists unrunnable models | one search; fit for all; Use for… |
| Runner | resume twins; Pause/Stop on recipes; silent-loss tests owed | page scope; run sheet; the soak as a check |
| Activity | spinners from four sources | the Step and Tool levels |
| Recipes window | — | all of it |
| Training | — | the window, the loop, 18 of 20 trainers |
| Segments | new region; live boxes; brush | #7111, orientation, orders, Find Words |

---

## 5. What the owner can test today

From what landed on `origin/integration` since 2026-11-25 (the 2026-11-27 dev release has most of it; items dated
11-28 need tonight's build).

1. **Segment editor keys** (#7033, #7083): in Select, Option-drag draws a new box and Control-drag is the lasso; with
   the Line tool a drag draws a line box and clicks still place a polygon; Change Kind is offered only for regions
   and lines.
2. **Join Lines in the Same Row** (#7071): in Edit › Segments, the Preview menu and a line's menu, with a preview.
3. **Make Region from Lines** removes the region it empties, in one undo (#6737); **Convert to Line** refuses a region
   that holds lines and says how many (#6740); **Move Into** offers the level above (#6600).
4. **Run Step on the selected segments** from the right-click menus, and an edited line reading itself again after a
   pause; a cloud-read line says it may be out of date (#6069).
5. **Activity:** a multi-page file is one row that opens to its pages; the filter tokens `kind:` and
   `started by: automatic` (#6441, #6583); the launch alert names the synced folder whose files are held (#6584).
6. **A run meeting a closed project is paused, not failed** (#7088): start a run, close the project, look in Activity.
7. **Missing originals** ask in an alert on the window once per open, not a strip (#7077); Locate Originals' folder
   grant (#7076).
8. **Launch** with a saved library on a volume that does not answer costs about a second (#7105).
9. **Models pane** filters with its own bottom field (#7095); six labels say Project, not Library.
10. **Search:** `entities:` returns entity hits only (11-28).
11. **Knowledge paragraph** (#6837 to #6840): dates lead a statement; a place is stated once and linked; a single
    unsure source is hedged; two contradicting statements are one sentence with both readings.

Not testable yet, though it may look landed: #7111 (none of its 14 parts), the Activity tree (#7118), spinners
(#7119), orientation (#7108), the Orders sheet (#7109), any Recipes or Training window, channels.

There are also **235 open issues labelled `needs-your-test`** (recipe-designer 33, source-model 30,
panes-workspaces 18, activity 14, sharing 13). Section 11 turns them into one list per phase rather than 235 loose
asks.

---

## 6. Overlaps and conflicts

**Specs that say the same thing twice**
1. Two files named `segment-editor.md` (`source/`, approved, and `ui/`, draft "awaiting approval"); both define Join,
   the Knife and cutting words. Plus `segment-editor-crud.md`, `segment-actions.md` (65 lines),
   `segment-representations.md` (says another spec wins), `line-editor.md`. Merge: `ui/segment-editor.md` into
   `source/segment-editor.md` as its Tools chapter, ids kept; `segment-actions.md` into the crud spec;
   `segment-representations.md` to a pointer.
2. Five training specs each claim the gate or the bake-off: `distillation.md` (the loop and the one gate),
   `training-and-evaluation.md` ("the one spec for how a person trains, evaluates and chooses"),
   `correct-measure-distil.md` (the step contract), `jobs-and-fine-tuning.md` (trainers and cards),
   `training-window.md` (the window). Merge `training-and-evaluation.md` into `distillation.md`; keep
   `jobs-and-fine-tuning.md` for places and trainers; keep `correct-measure-distil.md` only as the contract a step
   fills; `training-window.md` is the UI.
3. Three "compare" features with one name (4.2). One spec section should name them: Compare tools on a step (with
   ground truth: a measure; without: agreement, labelled so), Compare prompts, Compare two runs.
4. `source/models-chains-and-projects.md` is 822 KB and `ui/activity-pane.md` 571 KB. Workers cannot hold them, and
   brief tag counts drift (the activity brief quotes 132/209/33; the file has 142/206/34). Split each by its
   Owns list before Phase 2.

**Rules that contradict**
5. The vocabulary: `activity-pane.md` and `recipes-run.md` say Stage, Card, Job; `recipes-window.md` and the windows
   spec say Recipe › Step › Tool; `ui/workflows.md` (approved 2026-11-02) defines a workflow on screen with a bar
   that builds a "chain"; `source/recipe-designer.md` "The words" defines Workflow as on-screen vocabulary.
   `activity.pane.children-are-what-it-works-on` and decision 2 contradict #7118.
6. `features.yaml` contradicts the 2026-10-04 ruling (2).
7. The `spec-research` brief opens with the 2026-11-21 ruling "Research lives in the main window's sidebar … not to
   be reworded" and at line 426 says the 2026-11-28 ruling replaces it with its own window. One brief, both rules.
8. The Models window ruling (2026-11-24: replaces the Settings panes) against the windows spec's question 8
   (Settings keeps caps and one link) against the code (the old view embedded whole).
9. Lane counts: `[loop].lanes = 12` in the live `harness.toml` against the standing rulings of 3 (11-22), 5 (11-26),
   7 and 9 (11-27). The `only` list names about 150 lanes, most finished.

**Lanes doing the same work**
10. #7111 is one queue step (`seg-draw` `batch-7111`, the full brief) and also three unqueued slices (7111a, b, c).
    Parts 11 to 14 are in no slice.
11. `seg-finish` and `seg-hang` both hold parked briefs for #7079; `seg-finish` holds briefs for #7081, #7082, #7083,
    which are closed. Five segment lanes (`seg-tools`, `seg-finish`, `seg-draw`, `seg-inspector`, `seg-hang`) plus
    `segments-rest` and `spec-seg-metadata` all edit `source/segment-editor.md`.
12. #7112 (`runner-reliability`) continues #6069, which is parked in `seg-tools`; its results show in the readings
    list that is #7111 part 3 (`seg-draw`).
13. `code-audit` (17 areas left: shell, library, inspector, reader, settings, onboarding, activity, workflows,
    recipes…) edits the same files as every product lane, by design skipping files with unlanded steps. Run it
    behind a phase, never beside it.
14. Orientation is in `seg-finish` (#7108) and in `spec-seg-metadata`; flows in `seg-inspector` (#7109) and
    `spec-seg-metadata`.
15. `spec-view-choosers` and `spec-affordances` describe the pane head, which the owner is polishing by hand in the
    `owner-polish` worktree (#6741). **Rule for this plan:** the pane head (the one menu button, the head's left,
    centre and right, the breadcrumb icons, the markup toolbar) is owner-polish work. No builder lane touches those
    files. The two specs are written as inputs to that session, inventory and recommendations only, and their build
    steps wait for the owner's result.
16. Six Fable spec lanes started or queued today (`platform-floor`, `spec-app-search`, `spec-research`,
    `spec-affordances`, `spec-seg-metadata`, `spec-view-choosers`) while 128 of the last four days' commits were
    already specs and 201 issues are labelled `needs-spec`. Three have been sent. Specs for areas outside the
    current phase make issues nobody will work for months.

---

## 7. The master order (why this order)

Each area stands on the one before.

1. **Segments, then the runner, then Activity** (Phase 1). Every later feature reads or writes segments; the runner
   makes them; Activity is how anyone knows the runner works. Activity's tree needs the engine to record a tool
   level, which is a runner change, so they are built together.
2. **Channels in Phase 1 too,** because they are what makes "polished" enforceable. Without them the only build is
   Dev and nothing is ever finished.
3. **The vocabulary before the Recipes window** (Phase 2). The window is the vocabulary made visible. Activity's
   labels, the Run Step menus and Set Up take the same names in the same phase, so no screen is renamed twice.
4. **The Models & Cluster window before Set Up and Compare** (Phase 2 to 3). Set Up proposes models; Compare runs
   them. Both are only as good as the list of what can run here and what is measured.
5. **Compare before Training** (Phase 3 to 4). Compare is the measure; training without the measure is
   unverifiable. Training's card, gate and Use This are Compare's result with one more candidate.
6. **Search and export late** (Phase 4): they are listed Release today and mostly work; they need exactness and a
   round-trip test, not design.
7. **The shell** (panes, sidebar, menus) is polished continuously by the owner-polish session and one builder lane
   that follows it, and closed in Phase 4.

Phases, lanes and issues:

| Phase | Lanes (max 6 writing) | Milestones and issues in it |
|---|---|---|
| 1 | `seg-draw` (#7111 then Find Words prep), `seg-finish` (#7108, #7115, #7034, #7080), `seg-inspector` (#7109); `runner-reliability` (#7112, finish 2 and 3, #6584, #6595, #5933); `activity` (#7118 with the engine tool level, #7119, finish 3); `channels` (new: section 2.1) and `triage` (new: section 11) share the sixth slot; `launch` finishes launch-2 then stops | `source-model` (segment issues), `segment-representations`, `recipes-run`, `activity`, `release-channels`, `engine-startup-lifecycle` |
| 2 | `vocabulary` (new: labels, specs, Find Words as a step, step and tool tiers), `recipes-window` (new), `models-window` (resume), `lane-ie` (image enhancement finish), `owner-bugs` (was `app-bugs`), one shell lane following owner-polish | `workflows`, `workflow-node-config`, `ai-settings`, `image-enhancement`, `panes-workspaces`, new `recipes-window` |
| 3 | `set-up` (recipe-designer), `compare`, `models-finder`, `cloud-caps`, `owner-bugs`, `training` (engine: the loop for the two steps) | `recipe-designer`, `readers-measured`, `cloud-permission-and-spend`, `read-any-hand` (measurement only) |
| 4 | `training-window`, `training` , `search`, `export`, `shell`, `owner-bugs` | `training-window`, `search`, `search-correct-and-fast`, `export-pipeline`, `export-roundtrip`, `library-view-modes`, `sidebar-crud`, `menus-and-commands`, `importer`, `undo-trash-rollback` |
| 5 | `release` (whole-app test, the lane, promotion), `docs` (manual builder), `owner-bugs` ×2, `perf`, `quality` | `release-and-versioning`, the `Bugs - *` and `Performance - *` buckets, `test-environment-contract`, `ui-test-harness` |

---

## 8. What to pause now, and the lane count

**Lane count: 6 writing lanes, plus at most 1 spec lane.** Reasons: the bottleneck is checks, trains and review
rounds on 4 check machines, not workers (the owner's own finding of 2026-11-22: about 10 landings in 11 hours with 14
workers; and the 2026-11-25 note of the Pro at load 200). Landings per day did not rise with lanes: 22 a day on
average over 14 days, with between 6 and 26 lanes landing on a day; 15 a day over the last four, with 7 to 13. Six lanes on one phase share
files on purpose, so they are batched in one train rather than colliding across a dozen areas. Drop the Pro as a
check runner (it is already "last"; it is also the manager's machine) and keep three.

**Keep (Phase 1):** `seg-draw`, `seg-finish`, `seg-inspector`, `runner-reliability`, `activity`, and one slot that
alternates `launch` (finish launch-2), then `channels`, then `triage`. `app-bugs` finishes `swift-base-reds-1` (red
tests on integration block every train) and then becomes the `owner-bugs` lane, used only for what the owner reports.

**Pause now, with what each resumes for:**

| Lane | Why pause | Resumes |
|---|---|---|
| `kg-readable-representation`, `kg-store-and-query` (and parked `kg-store`, `kg-render`, `kg-teach`) | not in 1.0; five landings a day of paragraph work | after 1.0 (one KG lane may run in Phase 5 if slots are free) |
| `read-any-hand` | product code for the flagship before the reader's basics are polished; keep only its measurement steps | Phase 3, measurement only |
| `canvas-organize` | not in 1.0; its spec's questions are unanswered | after 1.0 |
| `code-audit` (17 areas left) | touches every product file | each area runs after the phase that owns it lands |
| `training` (1b) | let 1b land (it is in a train), then stop | Phase 3 |
| `lane-ie` | finish `ie-finish-1`, then stop | Phase 2 |
| `lane-qwen` | a trial; no product | when the owner asks |
| `spec-research`, `spec-affordances` (queued, not sent) | hold | `spec-affordances` as an input to owner-polish this week if the owner wants it; `spec-research` after 1.0 |
| `spec-app-search`, `platform-floor`, `spec-view-choosers` (sent) | let each finish its one step; file no build issues from them yet | search in Phase 4; the floor decision in Phase 5; view choosers feed owner-polish |
| `spec-seg-metadata` (queued) | **run it**, as the one spec lane: Phase 1 needs it | now |
| `builder-plan`, `builder-fixes`, `builder-speed`, `agent-profiles`, `credit-stop`, `ci-actions` (parked) | the builder gets one lane's worth of work, chosen from section 10, nothing else | section 10's steps, in order |

Also: set `feed_milestones` to stay false until the roadmap file drives it (section 10); cut `[loop].only` to the
lanes above; delete the stale parked briefs for closed issues (#7079, #7081, #7082, #7083 in `seg-finish` and
`seg-hang`).

---

## 9. The pace, and how long each phase is

Measured from `journal.jsonl` (event `queue`, state `landed`) and GitHub:

| Measure | Value |
|---|---|
| Landings, 2 – 28 Nov | 544 |
| Landings a day, last 14 days | 22 (range 8 to 40) |
| Landings a day, last 4 days | 15 (12 to 20) |
| Of those, product (app or engine a person sees), by commit subjects since 25 Nov | about a third: 5 to 8 a day |
| Issues closed a day, last 14 days | 13 (188 in 14 days; two days of 37 and 69 are bulk closes) |
| Issues opened a day, last 14 days | 37 (513; 187 on 21 Nov alone, from spec steps filed as issues) |
| Net | the backlog grows by about 23 a day |

With six lanes on one phase, the product share should be most of the landings: assume **10 to 14 product landings a
day**, each a batch closing **2 to 4** issues or spec lines (the 2026-11-24 rule). That is 20 to 55 a day; plan on
**25, with a range of 15 to 40**.

| Phase | Work (issues and spec lines in scope, after triage) | At 15 / 25 / 40 a day | Planned |
|---|---|---|---|
| 1 | about 330: segments 90, runner 60, Activity 120 (tests owed on PARTIAL lines dominate), channels 30, launch 10, triage bookkeeping 20 | 22 / 13 / 8 working days | 3 weeks |
| 2 | about 300: vocabulary and labels 40, Recipes window 60, Models window 70, image enhancement 35, shell 95 | 20 / 12 / 8 | 4 weeks (holidays) |
| 3 | about 280: Set Up 100, Compare 40, finder 50, caps 20, training engine 70 | 19 / 11 / 7 | 4 weeks |
| 4 | about 360: training window 60, search 40, export 30, shell and library 180, importer and undo 50 | 24 / 14 / 9 | 4 weeks |
| 5 | about 250: release 40, bugs and performance 110, tests 60, docs 40 | 17 / 10 / 6 | 4 weeks |

The planned lengths sit between the slow and the middle rate because the real gate is the owner's testing, not the
builder. If Phase 1 runs at the slow rate, every later date moves by about 9 working days; section 10's ETA view is
what would show that in the first week.

---

## 10. The roadmap as data the builder runs from

Today the pieces exist but are not joined: `build-order.md` (49 milestones in order, edited from the console by
`builder order`, `order.py`); `builder milestone` (`milestone.py`: a milestone's open issues as one cluster brief per
build-order step, a question for anything it cannot place; the console's `start-milestone` verb, `console.py:294`);
lanes already carry `milestone` (`queue.py:297`); the console has `/api/milestones` (`console.py:830`), `/api/progress`
(`spec_ok_series`, `:167`, the [OK] count of each spec over time) and `/api/release`; `[loop].only`, `lanes` and
`feed_milestones` are re-read every tick (`queue.py:2975`, `:3050`).

**The one new file:** `roadmap.yaml` (proposed, to sit beside `build-order.md`).

```yaml
phases:
  - id: phase-1
    title: Solid ground
    ends: 2026-12-20
    release: Alpha 1
    lanes: 6
    exit: "Run Find Regions, Find Lines and Read on 200 pages, quit mid-run, relaunch, it resumes; …"
    owner_tests: [ ... ]            # the list in section 12, by id
    graduates: {segment-editor: alpha, runner: alpha, activity: alpha}
    milestones: [source-model, segment-representations, recipes-run, activity, release-channels]
    document: ["manual: your-first-project", "video: core-loop-private"]
public:                              # what the site and manual may show
  - {phase: phase-1, theme: "Reading and correcting a page", quarter: "2026 Q4"}
```

**Builder changes, as small steps in order** (each one landing):

1. **ETA and history view** (first, because the owner asked for it and it needs no other step). Data: the journal's
   landed rows; GitHub open and closed counts per milestone (already read for `/api/milestones`); the new History
   tab's DuckDB index. Method: for each milestone, phase and the whole 1.0 set, `remaining ÷ rate`, where the rate is
   net closes a day (closed minus opened) over a trailing 7-day and 14-day window, bootstrapped by resampling the
   days, shown as a **range: the 20th, 50th and 80th percentile dates**, never one date. When the net rate is zero or
   negative it says "not converging: N opened, M closed a day". Beside it, the history: open count per phase per
   day, landings per day split product / builder / spec, and the date each estimate was made, so a slipping
   estimate is visible as a line that moves right. Shows: a Roadmap page in the console, one line in the 15-minute
   status text, and `builder eta --json`.
2. `builder roadmap check`: reads `roadmap.yaml`; refuses a milestone that is in no phase, in two, or not in
   `build-order.md` or on GitHub; refuses a phase with no exit.
3. The loop takes `only` and `lanes` from the current phase when `[loop].from_roadmap = true` (a hand-named lane and
   the `owner-bugs` lane still run). The current phase is the first whose milestones have open issues.
4. `feed_milestones` restricted to the current phase: when a lane is free, `builder milestone <m> --enqueue` for the
   phase's first milestone with open issues, batching 3 to 5 issues a step (already its cluster rule).
5. Each lane and step row carries `phase` and `tier` (from `features.yaml` via the milestone), shown in the console
   and the status text.
6. The Roadmap page: per phase, open and closed issues, the [OK] share of its specs' lines (reuse `progress_view`),
   the owner's test list with ticks, the ETA range, and the drift against `ends`.
7. A graduation guard: `features.yaml` may not raise an area to Beta while its spec has `[GAP]` or `[BROKEN]` lines
   in its declared 1.0 scope or an open P0/P1 in its milestone; to Release without two weeks at Beta.
8. Release notes gain "Graduated in this build" per channel (the notes generator exists and is [OK]).
9. `builder triage` in bulk (section 11), each change a reason row in the journal.

---

## 11. The backlog to zero

**The numbers.** 2,235 open issues in 101 milestones (108 milestones exist); 235 in no milestone; 235 labelled
`needs-your-test`; 201 `needs-spec`; 37 `needs-your-decision`; 536 not updated since 1 November; 136 are spec build
steps filed as issues ("… Step N.M"). By label: 486 bugs, 334 features, 95 tasks, the rest unlabelled.

### 11.1 Triage first (estimates, to be replaced by the triage's own counts)

| Class | Estimate | How it is decided | What happens |
|---|---|---|---|
| Built, waiting for the owner | 235 (`needs-your-test`) | already labelled | moved onto the phase test lists (section 12). Closed when the owner ticks it, or (owner decision, question 14) when it has shipped in a Beta build for 14 days with no reopen |
| Already fixed, or a duplicate | 250 to 350 | a landed commit cites it (`Fixes`/`Part of` with the behaviour now `[OK]`), or the title matches a closed issue, or its spec line is `[OK]` with a test | closed with the commit and the test named |
| Obsolete: superseded by a ruling or a spec | 150 to 200 | the feature it names was retired (modes, the old Settings panes, word readings, per-tier builds), or its milestone is a retired bucket | closed with the ruling or spec line cited |
| Belongs to a roadmap phase | 900 to 1,050 | its milestone or `spec:` label maps to a phase (11.2) | moved to that phase's milestone |
| After 1.0 | 450 to 550 | its milestone is in the After 1.0 set (11.2) | one milestone, `After 1.0`, keeping the `spec:` label |
| Builder and test harness | 150 to 180 | milestone `Builder`, the testing milestones | one track, one lane's worth at a time |

**Done by the builder, safely.** A `triage` lane runs `builder triage` in batches of 50. For each issue it writes a
**reason row** (issue, class, evidence: a sha, a spec id and tag, a duplicate's number, or a ruling's date) to the
journal and as a comment, then applies the change. Nothing closes without a row. The owner's rule "update issues,
don't close them" holds: where a residue survives, the issue is retitled to the residue and kept, with a comment
saying what was done; only an issue with no residue closes. Closes are reviewed by a second model on a 10 per cent
sample; any class it disagrees with is redone. The owner sees one page: counts per class, the sample, and an Undo
(reopen) for each batch. Anything the triage cannot place is a question, never a guess (the rule `builder milestone`
already follows). Two days of one lane.

**Stop the inflow.** A spec's build steps are no longer filed as one issue each before their phase: a step becomes an
issue when its phase starts. That alone removes most of the 37 a day.

### 11.2 From 108 milestones to 13

GitHub milestones stay the spec-sized unit the builder reads (`milestone.py` finds a spec by its `> Milestone:` line),
so the merge is done in two stages: first the mapping in `roadmap.yaml` (no churn; the console groups by phase), then
the real merge once `builder milestone` selects by the `spec:<slug>` label, which several hundred issues already have.

| Target | Takes (open issues today) |
|---|---|
| 1 `1.0 Segments and the page` | source-model 208, segment-representations 17, reader-view 29, preview-surface 25, preview-image-editing 9, preview-magnifier 5, reading-markup-annotations 11, reader-overlay-frame-identity 3, editable-reader 1, panes 8 |
| 2 `1.0 Run and watch` | recipes-run 66, activity 56, engine-startup-lifecycle 28, responsiveness 5, Sidebar & Launch Performance 8, Performance - Engine 18, Performance - SwiftUI 13 |
| 3 `1.0 Recipes` | workflows 55, workflow-node-config 12, recipe-designer 98, image-enhancement 8 |
| 4 `1.0 Models` | ai-settings 50, cloud-permission-and-spend 9, readers-measured 11 |
| 5 `1.0 Teach` | read-any-hand 21 (measurement), training issues now in remote-compute and Later |
| 6 `1.0 Shell` | panes-workspaces 112, modes-to-panes 22, library-view-modes 80, sidebar-crud 41, menus-and-commands 16, UX - Mac 7, about 5, Keyboard Navigation 1, Library View 2, Inspector View 1, UX - Library & Reading Surface 2 |
| 7 `1.0 In and out` | importer 39, undo-trash-rollback 14, search 17, search-correct-and-fast 10, export-pipeline 15, export-roundtrip 4, historical-text-normalization 19 |
| 8 `1.0 Release and channels` | release-channels 6, release-and-versioning 12, version-and-contract-integrity 3, xcode-build-configs 4, App - Release & Distribution 3 |
| 9 `1.0 Quality` | Bugs - * (56), Lint 1, audited-action-layer 22, observable-data-layer 12, write-layer 7, transport-http-uds 14, test-environment-contract 29, ui-testing-strategy 22, ui-test-harness 16, code-organization 6, Testing Overhaul 2 |
| 10 `Builder` | Builder 80, Developer - Dev Experience 3 |
| 11 `Beta: Knowledge` | kg-tables 45, kg-readable-representation 27, kg-entity-inspector 18, kg-enrichment 15, kg-confidence-and-provenance 12, kg-rendering 7, kg-store-and-query 5, kg-lenses 3, hermeneutic-layer 4 |
| 12 `Beta: Sharing and devices` | Sharing & Pairing 45, sharing-people-and-machines 2, Engine - Sharing 1, Engine - Onboarding 2, Engine - Embed iOS 10, iPhone 10 |
| 13 `After 1.0` | research 44, research-operations 14, people-and-lives 18, concepts-and-terms 17, reconstruct-the-record 10, explore 15, iiif 18, remote-compute 48 (less training), automation 3, applescript 2, docs-citations 6, Mac App Store 3, Later 9, cand 14 11 |
| triaged away | Next release 81, cand 16 12, (none) 235: each issue goes to one of the above |

### 11.3 Focus: swarm one phase

One phase at a time; within it, the lanes of section 7; each lane works its milestone through
`builder milestone --enqueue`, one cluster brief per build-order step, 3 to 5 related issues a step, one check per
batch, the phase's lanes ridden in one train. Six lanes. The `owner-bugs` lane takes whatever the owner reports,
batched 3 to 5, and is the only lane allowed outside the phase.

### 11.4 The burn-down

After triage, about 1,000 issues stand between today and 1.0 (targets 1 to 9), plus the builder's 170.
At a net 25 a day (range 15 to 40) that is 40 working days (25 to 67): **mid-February to early April**, which is why
1.0 is set for April with the last phase as slack. Zero means: zero open in the nine 1.0 milestones, zero in no
milestone, and everything else in `Builder`, the two Beta milestones or `After 1.0` on purpose.

The console shows (step 1 of section 10): open count per phase over time as stacked lines; opened and closed per
day; the ETA range per phase and to zero; and the triage's class counts. The History tab is its data source.

---

## 12. Owner test lists (each phase ends with one)

**Phase 1 (Alpha 1)**
1. Import a folder of 200 page photos; the window is usable in under 2 seconds at the next launch.
2. Run the default recipe; in Activity expand Run → Step → File → Tool; the row being worked on is highlighted.
3. Quit mid-run; relaunch; the alert offers Resume; no twin job; counts continue.
4. Pause, Stop and Continue a recipe run; each does what it says within 5 seconds.
5. No spinner is left turning after the run ends, on any folder depth, after an engine restart.
6. Every one of #7111's 14 parts, by its number.
7. Draw a new region (#7034); boxes appear page by page during a run (#7115); set a line's orientation (#7108).
8. Select 3 lines, Run Step › Read on them with a chosen input reading (#7112); the new reading is listed and can be
   made current.
9. Settings › General: choose Alpha, relaunch, the About window says Alpha; choose Beta, the Dev-only surfaces go.
10. The triage page: 20 sampled closes, each with a reason you agree with.

**Phase 2 (Beta 1)**: the Recipes window opens on this project's recipe; a Step shows its Tool; a compound tool opens
on the canvas; no screen says workflow or chain; Find Words appears as an Alpha step with a badge; the Models &
Cluster window lists what this Mac can run with fit for every row; add a model by address; image enhancement from
all three doors; a fresh Mac on the Beta channel does Phase 1's list.

**Phase 3 (Beta 2)**: Set Up on three new projects (print, a clear hand, a hard hand) proposes a recipe with reasons;
Compare on five pages with no corrections says "agreement"; after correcting 100 lines it shows CER and WER; Use
This changes the step and its name; a cloud reader asks for permission and stops at its cap; the finder returns a
reader for Spanish, Latin and one non-Latin script, each marked measured or unmeasured.

**Phase 4 (Beta 3)**: Teach a reader on this Mac from 100 corrected lines, with a time estimate, pause and resume;
the card shows held-out CER beside the old reader; Use This and Undo; draw 30 regions and teach the region finder;
search for a word you corrected and find it; export a project and import it into an empty one with nothing changed.

**Phase 5 (1.0)**: a clean Mac, the Release channel, the manual open beside it: follow the manual's first four
chapters and report every place the app and the book differ.

---

## 13. Questions for the owner

Each has a recommended answer; the plan is written to the recommendations.

**Vocabulary**
1. Is a Tool allowed to be made of Tools (a compound tool), with a Step using exactly one Tool? **Yes** (3.3).
2. On screen, do we say "compound tool", or only "Tool" with "made of 3 tools" under it? **Only "Tool".**
3. The bar that runs several things over a selection: what is its unsaved chain called? **"Run steps…", and saving
   it makes a Recipe.**
4. Does Set Up keep "Stage" for a page that groups steps? **Yes, in Set Up only** (the windows spec's question 3).

**Trainable everything**
5. Is "every unit that runs a model is trainable" a 1.0 promise, or a rule each step meets when its trainer exists?
   **The second: 1.0 trains Read a Line and Find Regions; every other step says "cannot be taught yet" with its
   reason, as `DISTIL` already does.**
6. Must every model-running step have an error measure in 1.0, even untrainable ones? **Yes for reading and finding
   steps; names, statements and catalogue get precision and recall after 1.0 (#5545).**
7. Without corrected lines, may Compare show "agreement between readers"? **Yes, labelled "agreement, not accuracy",
   with a prompt to correct 20 lines for a first measure** (lower the 100-line floor to a stated small-sample range).

**Release and channels**
8. Is 1.0 as defined in section 1, with teaching as badged Beta inside it? **Yes.**
9. A public beta at Beta 1 (17 January)? **Yes, announced on the site only; no wider notice until Beta 2.**
10. What does the public download default to from Alpha 1? **Alpha until Beta 1, then Beta, then Release at 1.0.**
11. Nightly builds: do they keep publishing publicly? **Nightlies go to the Dev channel only; Alpha and Beta are
    promoted by hand from a nightly the owner tested** (this reverses the 2026-11-18 "every nightly is published
    with `--public`").
12. Apply the 2026-10-04 tier moves and add the missing areas to `features.yaml` now? **Yes, in Phase 1.**
13. Do recipe steps and tools carry tiers, with `check_recipe` reporting and Start skipping a hidden step? **Yes**
    (2.2).

**Backlog**
14. May a `needs-your-test` issue close by itself after 14 days in a Beta build with no reopen? **Yes, with a
    comment; the owner's tick closes it sooner.**
15. May the builder close "already fixed", "duplicate" and "obsolete" issues in bulk, each with a reason row and a
    10 per cent review? **Yes.**
16. Merge to 13 milestones (11.2), in two stages? **Yes.**
17. Stop filing a spec's steps as issues until its phase starts? **Yes.**

**Focus**
18. Six writing lanes and one spec lane, on one phase, until Alpha 1? **Yes; review the number on 20 December
    against the ETA view.**
19. Pause the knowledge-graph, read-any-hand product steps, canvas organise and the code audit now (section 8)?
    **Yes.**
20. Of the six Fable spec lanes: run `spec-seg-metadata` now, let the three already sent finish, hold
    `spec-research` and `spec-affordances`? **Yes; `spec-affordances` and `spec-view-choosers` report to the
    owner-polish session and file no build steps.**
21. Drop the Pro as a check runner? **Yes.**
22. Is the pane head wholly the owner's, with no builder lane on those files until the owner says? **Yes.**

**Scope**
23. Find Words in 1.0 as Beta; characters Alpha; strokes after 1.0? **Yes.**
24. Does the Models window search every step's models, or only reading, for 1.0? **Reading, Find Regions and Find
    Lines; other steps list installed and provider models without an online search.**
25. Training on a cluster or Hugging Face Jobs in 1.0? **No: this Mac only; Hugging Face Jobs stays Alpha.**
26. The macOS floor: stay on 26 for 1.0? **Decide from the `platform-floor` spec in Phase 5; assume 26.**
27. Sharing between two Macs: out of 1.0? **Out; Beta after.**
28. Research as its own window (2026-11-28): its spec lane waits until after 1.0? **Yes.**
29. Split `activity-pane.md` and `models-chains-and-projects.md`, and merge the segment and training specs (6)?
    **Yes, in Phase 1 and 2, one spec lane.**
30. The public roadmap on the site: themes and quarters, no dates? **Yes.**

Questions already open in specs that this plan depends on: the eleven in `ui/windows-models-recipes-training.md`
(1 and 2 answered 2026-11-28; 4 to 11 open, each with a recommendation there); the open questions in
`ui/canvas-organize.md` (paused); the layout question the `spec-app-search` brief was told to pose.

---

## 14. The next 48 hours

**Today, Saturday 28 November**
1. The owner reads sections 1, 3 and 13 and answers what they can; unanswered questions take their recommendations.
2. Manager: set `[loop].lanes = 6`; cut `only` to `seg-draw`, `seg-finish`, `seg-inspector`, `runner-reliability`,
   `activity`, `launch`, `app-bugs`, `spec-seg-metadata`; pause the lanes in section 8; hold the two unsent spec
   lanes; take the Pro out of `[check].remote`. Let what is in a train land.
3. Remove the stale parked briefs for closed issues from `seg-finish` and `seg-hang`; make #7111 one step with the
   a, b, c slices folded in and parts 11 to 14 added as a second batch.
4. Queue, in order, behind the running steps: `app-bugs` `swift-base-reds-1` (unblocks every train);
   `activity` #7118 with the engine's tool level first; `activity` #7119 as "one source: the engine's tree";
   `runner-reliability` #7112.
5. Tonight's nightly is the build for section 5's test list.

**Sunday 29 November**
6. One builder step: the ETA and history view (section 10, step 1).
7. One spec step (Fable): write `roadmap.yaml`, apply the vocabulary answer to "The words" in
   `windows-models-recipes-training.md`, `recipes-window.md`, `recipe-designer.md`, `workflows.md` and
   `activity-pane.md` (decision 2), and add the channel UX lines of 2.3 and the step and tool tiers of 2.2 to the
   channels spec. No code.
8. Start the `triage` lane on its first 200 issues, read-only: it proposes classes and reason rows and changes
   nothing. The owner reviews the page.

**Monday 30 November**
9. With the owner's yes on question 15, the triage applies its first batches.
10. Start the `channels` lane: `features.yaml` rows and moves; the Settings popup; the run-time tier.
11. The owner tests section 5's list on the 28 or 29 November build and reports; reports go to `owner-bugs` in
    batches.
12. First ETA reading: Phase 1's range against 20 December. If the 50th percentile is past 3 January, cut Activity's
    PARTIAL-test backfill from Phase 1 to Phase 2 and say so.

---

## 15. Spec coverage: deleted `agent-work/` files and code

`code-audit-2` landed on 2026-11-28 in 15 commits under #115: 429 paths ever existed under `agent-work/`, 6 remain,
about 205 were deleted in this cleanup. Its one "folded" output is
`docs/contributor_manual/design/carried-from-working-notes.md` (398 lines, about 20 findings), which says of itself
"nothing here is a behaviour line", plus four small spec edits. This audit read about 45 of the deleted design, spec,
plan and review files and checked about 25 against the specs by search. No DONE table was found in the journal, so
the commit messages were taken as the worker's claim. "Inferred" means a search found no home; the spec was not read
in full. This is a list only; no spec was written. It overlaps `code-audit-2` by design: that lane decided what to
delete; this checks its "already superseded" verdicts.

**Verdict.** Most deleted files are covered or truly obsolete. The claim is weak where the file held a security or
contract decision rather than a layout.

### 15.1 Decisions with no spec home, or a partial one

| # | Area | Deleted file (under `agent-work/`) | Commit | The decision or design | Spec it should go in | Phase |
|---|---|---|---|---|---|---|
| 1 | Sharing | `superpowers/specs/2026-07-14-sharing-always-on-design.md` | 7bb7f4de76 | Sharing is always on with no enable toggle; whole libraries only; "Share this library" is one action that does its own setup; an empty share set refuses connections; the two owner rows merge | `transport/multiuser-always-on.md` (owner resolution is there; "whole libraries only" and the one action are not) | after 1.0 |
| 2 | Sign-in | `superpowers/specs/2026-07-14-keychain-and-share-sheet-design.md` | 3dbab6748b | A synced enrolment secret mints per-device tokens; per-device revocation survives; invitations weighed against a co-present QR code | `transport/ios-sign-in.md` (partly) | after 1.0 |
| 3 | Sandbox | `superpowers/specs/2026-07-13-mac-app-store-sandbox-research.md`, `…-mas-sandbox-spike-result.md` | 836cfbfcbc | The sandboxed engine inherits the app's sandbox; the library folder is handed over by security-scoped bookmarks; one app, two as the fallback | `harness/release-and-versioning.md` or the channels spec (today it lives only in an entitlements file's header) | 5 |
| 4 | Libraries | `specs/library-location-grants-and-keychain-states.md` | b6e91e7476 | A library may be anywhere; a folder grant is minted only from a panel the person used; three keychain states | `harness/engine-startup-lifecycle.md` (inferred: no line says "only from a panel"; #7076 and #7092 just fixed bugs in exactly this) | 1 |
| 5 | Reader | `superpowers/specs/2026-07-14-reader-view-audit-and-design.md` | 3dbab6748b | Seven answered questions, among them: the Reader's transcript is read-only, no split inside one pane, a windowed transcript for very large folders | `ui/reader-view.md` (inferred) | 2 |
| 6 | Navigation | `superpowers/specs/2026-07-12-navigation-system-design.md` | 836cfbfcbc | One serialisable Location (document, page, box, statement, entity, surface), one resolve route, the MCP reveal tool | `ui/panes-workspaces.md`; the code exists (`LocationService.swift`, the MCP tool) with no spec for its contract | 2 |
| 7 | Recipes | `specs/2026-07-16-paleography-transcription-workflow.md` | b6e91e7476 | Models check each other, never themselves; disputed spans go to a stronger model; zooming in as the accuracy lever | `ui/workflows.md` (partly); it is the first worked example of a **compound tool** and belongs in the vocabulary spec | 2 |
| 8 | Knowledge | `specs/ontology-owning-library-plan.md`, `specs/global-library-scope-sweep.md` | b6e91e7476 | A window's views read the window's library, never the reserved global one (a bug met four times) | a rule in `ui/panes-workspaces.md` (inferred: no such rule found) | 2 |
| 9 | Maps | `specs/map-lens-needs-coordinates.md` | b6e91e7476 | The map had nothing to plot because the geocoding step was missing; the offline gazetteer is tiny | `source/maps-and-georeference.md` (inferred) | after 1.0 |
| 10 | Data model | `plans/datasets-and-records-spec.md` | b6e91e7476 | Structured data through prototypes and attributes; a first draft with new record types was rejected | `source/structured-data.md` (not verified that the rejection is recorded) | after 1.0 |
| 11 | Settings | `superpowers/specs/2026-07-13-settings-typography-ia-design.md` | 3dbab6748b | Settings laid out anew; reader and editor typography | `ai/ai-settings.md` has one sentence; no Settings spec owns typography (inferred) | 4 |
| 12 | Affordances | `superpowers/specs/2026-07-14-ux-critique-toggles-and-pairing.md` | 7bb7f4de76 | An audit of every Settings toggle and an inventory of places the UI silently shows nothing | the `spec-affordances` lane's spec: hand it this file | now (input to owner-polish) |
| 13 | Search | `plans/SEARCH_PLAN_2026-08-19.md`, `plans/search-s2-implementation-plan.md` | b6e91e7476 | The staged search plan | `ui/search.md` cites a plan; per-stage decisions not verified: hand both to `spec-app-search` | 4 |
| 14 | Import | `design/legacy-10-import-review.md` | 772a64cbb2 | Importing an old archive in place without copying it (the file names private research material: path only) | `importer/importer.md` (the in-place case not verified) | 4 |

Rows 1 to 6 are the strongest candidates for `[GAP]` lines. Rows 12 and 13 cost nothing: the two spec lanes already
running should be given the deleted files as sources.

Covered, as a sanity sample: feature gating → `harness/release-and-versioning.md`; the image-editing design →
`ui/preview-image-editing.md`; edit states as renditions → `source/image-enhancement.md`; the Kraken segmenter
evaluation → `ai/local-runtimes.md`; the cluster connection plan → `compute/hpc-runner-acenet.md`; the sidebar review →
`ui/sidebar-crud.md`; the Inspector's tabs → `source/panes.md`; the engine package layout →
`harness/code-organization.md`.

### 15.2 The eight deleted code files

| File | What it was | Now |
|---|---|---|
| `experiments/kraken/kraken_segment.py` (123 lines) | Kraken's neural segmenter run in a scratch environment, dumping each line's baseline and polygon with the pixel frame it was measured on | **In the product**: Kraken is the default line finder (`recipes/regions.py`, `llm/kraken_runtime.py`). The "every box names its frame" rule is `ui/reader-overlay-frame-identity.md`. Nothing lost |
| `experiments/kraken/RecognizeDocuments.swift` (151 lines) | The newer Apple document-structure request (lines, paragraphs **and words** as containers), which only Swift can call | **In the product**: `fichero-server/bin/fm-bridge/FmBridge.swift`, `media/ocr_geometry.py`, `ai/local-runtimes.md`. Whether its **word** containers are stored as word segments was not verified; if they are not, it is a second word-box producer for print, beside the reader's cuts. Give this to `spec-seg-metadata` |
| `experiments/kraken/overlay_report.py` (296 lines) | Kraken lines drawn beside Apple Vision boxes and scored on the same pages (it recorded Vision returning 403 "lines" for 966 words on one page) | **Partly lost**: the comparison lives on as Compare Readers; the scored, drawn overlay as a repeatable check does not. It is the natural test for Find Lines' missing measure (4.7). Put a line in `source/readers.md` (milestone `readers-measured`), Phase 3 |
| `bbox-lab/lab2.py` (909 lines) | Five experiments on Apple Vision boxes: known text fed into the geometry merge; re-reading each line on an enlarged crop; overlapping strips; a sweep of request settings; clustering word boxes into lines | **Partly in the product**: text-guided alignment is `media/geometry_merge.py` and Tie Text to Lines. The enlarged-crop second pass and the strips have no spec line (inferred from a search of `segments-and-geometry.md` and `readers.md`); their measured results went with the file. One `[GAP]` line each in `source/readers.md` if the numbers still matter; otherwise record that they were tried. Its docstring names private research material |
| `specs/lance-ext-migration/*.draft.py` (4 files) | A drafted move of vector search from the LanceDB client to DuckDB's Lance extension through the one connection, with an idempotent rebuild and a parity test, gated on a go/no-go | **Not done and not specified**: `db/__init__.py` still imports `lancedb`; `OPEN-QUESTIONS.md:56` records only that LanceDB is derived data. The decision (do it, or not) has no home. One question in `kg/kg-store-and-query.md` or `ui/search.md`; after 1.0 unless search correctness needs it |

**For word, character and stroke boxes:** nothing in the deleted experiments produced strokes or characters. The
experiments' lasting findings are that Apple's older request fragments handwriting into false lines (so it is a
print-only line finder, which the product already assumes) and that the newer request returns word containers. Word
boxes for handwriting come from the reader's cuts (3.7); for print, the newer Apple request is the candidate.

### 15.3 In the roadmap

"Write the missing specs" is one spec-lane step per phase, never a lane of its own: Phase 1, rows 4 and the Apple
word-container question (into `spec-seg-metadata`); Phase 2, rows 5 to 8; Phase 3, the line-finder measure; Phase 4,
rows 11, 13, 14; Phase 5, row 3; after 1.0, rows 1, 2, 9, 10 and the vector-store question.
